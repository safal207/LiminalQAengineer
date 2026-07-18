#!/usr/bin/env python3
"""Validate the LiminalQA × Lotus evidence vertical-slice example."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN_PATH = ROOT / "integrations/lotus/examples/airbnb-run-001.json"
TRACE_PATH = ROOT / "integrations/lotus/examples/airbnb-run-001.ttrace.jsonl"
MANIFEST_PATH = ROOT / "integrations/lotus/examples/airbnb-run-001.evidence-manifest.json"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GRADES = {"F0", "F1", "F2", "F3", "F4", "F5"}
CLAIM_KINDS = {"fact", "observation", "hypothesis"}


class ContractError(ValueError):
    """Raised when a vertical-slice invariant is violated."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return value


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_run(run: dict[str, Any]) -> None:
    required = {
        "schema_version", "run_id", "status", "target", "source_base",
        "protocol_pins", "claims", "lotus", "drp_decision",
        "liminaldb_projection", "evidence_manifest",
    }
    missing = sorted(required - run.keys())
    if missing:
        raise ContractError(f"run: missing fields: {missing}")

    if run["schema_version"] != "lqa-lotus-run/0.1":
        raise ContractError("run: unsupported schema_version")

    if not SHA_RE.fullmatch(run["source_base"]["head_sha"]):
        raise ContractError("run: source_base.head_sha must be a full Git SHA")

    names = set()
    for pin in run["protocol_pins"]:
        if not SHA_RE.fullmatch(pin["commit_sha"]):
            raise ContractError(f"run: invalid protocol pin for {pin.get('name')}")
        names.add(pin["name"])
    expected_names = {"T-Trace", "DRP", "ProofPath", "LiminalDB"}
    if names != expected_names:
        raise ContractError(f"run: protocol pins must equal {sorted(expected_names)}")

    seen_kinds = set()
    for claim in run["claims"]:
        kind = claim.get("kind")
        grade = claim.get("evidence_grade")
        if kind not in CLAIM_KINDS:
            raise ContractError(f"run: invalid claim kind {kind!r}")
        if grade not in GRADES:
            raise ContractError(f"run: invalid evidence grade {grade!r}")
        seen_kinds.add(kind)
    if seen_kinds != CLAIM_KINDS:
        raise ContractError("run: example must distinguish fact, observation, and hypothesis")

    pythia = run["lotus"]["pythia"]
    if run["status"] == "planned" and pythia["confirmed_defect"]:
        raise ContractError("run: planned run cannot claim a confirmed defect")
    if pythia["confirmed_defect"] and pythia["verdict"] == "ESCALATE":
        raise ContractError("run: ESCALATE cannot be a confirmed defect")

    decision = run["drp_decision"]
    if decision.get("run_id") != run["run_id"]:
        raise ContractError("run: DRP decision must reference the same run_id")
    if decision.get("supersedes_record_id") == decision.get("record_id"):
        raise ContractError("run: a DRP record cannot supersede itself")

    projection = run["liminaldb_projection"]
    if projection.get("append_only") is not True:
        raise ContractError("run: LiminalDB projection must be append-only")
    if projection.get("entity_id") != run["run_id"]:
        raise ContractError("run: LiminalDB entity_id must match run_id")
    if "valid_time" not in projection or "transaction_time" not in projection:
        raise ContractError("run: both temporal axes must be explicit")


def load_and_validate_trace(path: Path, run_id: str, decision_id: str) -> None:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ContractError(f"trace:{line_no}: invalid JSON: {exc}") from exc

    if [record.get("type") for record in records] != ["sense", "transition", "commit"]:
        raise ContractError("trace: required order is sense -> transition -> commit")

    ids = [record.get("id") for record in records]
    if len(ids) != len(set(ids)):
        raise ContractError("trace: ids must be unique")

    timestamps = [parse_ts(record["ts"]) for record in records]
    if timestamps != sorted(timestamps):
        raise ContractError("trace: timestamps must be monotonic")

    if any(record.get("thread_id") != run_id for record in records):
        raise ContractError("trace: every record must use the run_id as thread_id")

    if records[-1].get("decision_ref") != decision_id:
        raise ContractError("trace: commit must reference the DRP decision")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("integrity_only") is not True or manifest.get("truth_claim") is not False:
        raise ContractError("manifest: integrity/truth boundary must be explicit")

    for artifact in manifest.get("artifacts", []):
        path = ROOT / artifact["path"]
        if not path.is_file():
            raise ContractError(f"manifest: missing artifact {artifact['path']}")
        actual = sha256_file(path)
        if actual != artifact["sha256"]:
            raise ContractError(
                f"manifest: SHA mismatch for {artifact['path']}: "
                f"expected {artifact['sha256']}, got {actual}"
            )


def validate_all() -> None:
    run = load_json(RUN_PATH)
    manifest = load_json(MANIFEST_PATH)
    validate_run(run)
    load_and_validate_trace(
        TRACE_PATH,
        run_id=run["run_id"],
        decision_id=run["drp_decision"]["record_id"],
    )
    validate_manifest(manifest)


def main() -> int:
    try:
        validate_all()
    except (OSError, KeyError, TypeError, ContractError) as exc:
        print(f"FAIL lotus evidence contract: {exc}", file=sys.stderr)
        return 1
    print("PASS lotus evidence contract (run + trace + decision + manifest + storage projection)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
