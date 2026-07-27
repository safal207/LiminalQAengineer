#!/usr/bin/env python3
"""Validate the causal deep-audit skill family without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

SKILLS = {
    "causal-deep-audit": ROOT / "skills/causal-deep-audit/SKILL.md",
    "evidence-capture": ROOT / "skills/evidence-capture/SKILL.md",
    "causal-adjudication": ROOT / "skills/causal-adjudication/SKILL.md",
    "cyber-causal-audit": ROOT / "skills/cyber-causal-audit/SKILL.md",
    "websocket-redis-lifecycle": ROOT / "skills/websocket-redis-lifecycle/SKILL.md",
    "exact-head-governance": ROOT / "skills/exact-head-governance/SKILL.md",
    "replay-memory": ROOT / "skills/replay-memory/SKILL.md",
    "product-impact": ROOT / "skills/product-impact/SKILL.md",
    "transition-next-action": ROOT / "skills/transition-next-action/SKILL.md",
}

SCHEMA = ROOT / "schemas/causal-deep-audit-packet.schema.json"
CYBER_SOURCES = ROOT / "skills/cyber-causal-audit/sources.json"
CYBER_AUDIT = ROOT / "audits/security/tradernet-repository-causal-review-v1.json"

REQUIRED_GLOBAL_TERMS = (
    "authority",
    "evidence",
)

FORBIDDEN_AUTHORITY_CLAIMS = (
    "the audit may merge",
    "the audit may deploy",
    "the audit may contact external parties",
    "missing evidence is success",
)



def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing opening frontmatter delimiter")
    try:
        _, raw, body = text.split("---\n", 2)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc

    data: dict[str, str] = {}
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {raw_line!r}")
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data, body



def validate_skill_text(expected_name: str, text: str) -> list[str]:
    errors: list[str] = []
    try:
        metadata, body = _frontmatter(text)
    except ValueError as exc:
        return [str(exc)]

    if metadata.get("name") != expected_name:
        errors.append(
            f"frontmatter name must be {expected_name!r}, got {metadata.get('name')!r}"
        )
    if len(metadata.get("description", "")) < 40:
        errors.append("description must explain the trigger and purpose")
    if len(body.strip()) < 500:
        errors.append("skill body is too small to define an auditable workflow")

    lowered = body.lower()
    for term in REQUIRED_GLOBAL_TERMS:
        if term not in lowered:
            errors.append(f"required global term missing: {term}")
    for claim in FORBIDDEN_AUTHORITY_CLAIMS:
        if claim in lowered:
            errors.append(f"forbidden authority claim present: {claim}")

    if not re.search(
        r"\b(not_run|needs_evidence|incomplete|blocked|hold|candidate)\b", lowered
    ):
        errors.append("skill must preserve at least one explicit uncertainty/fail-closed state")

    return errors



def validate_schema(schema: dict) -> list[str]:
    errors: list[str] = []
    required = set(schema.get("required", []))
    for field in ("source_identity", "authority", "verdict", "evidence_ledger", "next_action"):
        if field not in required:
            errors.append(f"schema missing required top-level field: {field}")

    try:
        states = set(
            schema["properties"]["verdict"]["properties"]["state"]["enum"]
        )
        evidence_states = set(
            schema["$defs"]["evidence"]["properties"]["status"]["enum"]
        )
        gates = set(
            schema["properties"]["verdict"]["properties"]["gate"]["enum"]
        )
    except (KeyError, TypeError) as exc:
        errors.append(f"schema verdict/evidence structure is incomplete: {exc}")
        return errors

    for state in ("NOT_RUN", "NEEDS_EVIDENCE", "INCOMPLETE", "HOLD"):
        if state not in states:
            errors.append(f"schema verdict states missing fail-closed value: {state}")
    for state in ("NOT_RUN", "UNAVAILABLE", "STALE", "INCOMPLETE"):
        if state not in evidence_states:
            errors.append(f"schema evidence states missing value: {state}")
    if gates != {"ALLOW_REPORT", "ESCALATE", "BLOCK"}:
        errors.append("schema gate enum must be exactly ALLOW_REPORT/ESCALATE/BLOCK")

    return errors



def validate_cyber_sources(payload: dict) -> list[str]:
    errors: list[str] = []
    policy = payload.get("adoption_policy", {})
    if policy.get("remote_runtime_execution") is not False:
        errors.append("cyber sources must disable remote runtime execution")
    if policy.get("mutable_branch_execution") is not False:
        errors.append("cyber sources must disable mutable branch execution")

    entries = payload.get("method_sources", [])
    if len(entries) < 5:
        errors.append("cyber sources must retain the reviewed methodology set")
    for entry in entries:
        repository = entry.get("repository", "<unknown>")
        if not re.fullmatch(r"[0-9a-f]{40}", entry.get("commit", "")):
            errors.append(f"cyber source {repository} is not pinned to an exact commit")
        if not entry.get("license") or not entry.get("license_path"):
            errors.append(f"cyber source {repository} is missing license metadata")
        if entry.get("adoption") == "EXECUTABLE_DEPENDENCY":
            errors.append(f"cyber source {repository} may not become executable by default")

    return errors



def validate_cyber_audit(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("status") != "STATIC_REVIEW_COMPLETE_RUNTIME_VALIDATION_PENDING":
        errors.append("cyber audit must preserve pending runtime validation")

    prohibited = set(payload.get("authority", {}).get("prohibited", []))
    for required in (
        "use credentials",
        "place or cancel orders",
        "mass subscribe or load test production",
        "claim an internal Tradernet root cause",
        "merge or deploy",
    ):
        if required not in prohibited:
            errors.append(f"cyber audit authority is missing prohibition: {required}")

    allowed_claims = {
        "OBSERVATION",
        "SECURITY_SIGNAL",
        "DEFECT_CANDIDATE",
        "RESOURCE_LEAK_CANDIDATE",
    }
    seen: set[str] = set()
    for finding in payload.get("findings", []):
        finding_id = finding.get("id", "")
        if not finding_id or finding_id in seen:
            errors.append(f"cyber audit finding ID is missing or duplicated: {finding_id!r}")
        seen.add(finding_id)
        if finding.get("claim_level") not in allowed_claims:
            errors.append(f"cyber audit finding {finding_id} overstates its claim level")
        if not finding.get("competing_explanations"):
            errors.append(f"cyber audit finding {finding_id} lacks competing explanations")
        if not finding.get("next_test"):
            errors.append(f"cyber audit finding {finding_id} lacks a discriminator")

    return errors



def _load_json(path: Path, label: str) -> tuple[dict | None, list[str]]:
    if not path.is_file():
        return None, [f"missing {label}: {path.relative_to(ROOT)}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"invalid {label} JSON: {exc}"]



def validate_repository() -> list[str]:
    errors: list[str] = []

    for name, path in SKILLS.items():
        if not path.is_file():
            errors.append(f"missing skill file: {path.relative_to(ROOT)}")
            continue
        for error in validate_skill_text(name, path.read_text(encoding="utf-8")):
            errors.append(f"{path.relative_to(ROOT)}: {error}")

    if not SCHEMA.is_file():
        errors.append(f"missing schema: {SCHEMA.relative_to(ROOT)}")
    else:
        try:
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid schema JSON: {exc}")
        else:
            errors.extend(f"schema: {error}" for error in validate_schema(schema))

    cyber_sources, load_errors = _load_json(CYBER_SOURCES, "cyber sources")
    errors.extend(load_errors)
    if cyber_sources is not None:
        errors.extend(
            f"cyber sources: {error}" for error in validate_cyber_sources(cyber_sources)
        )

    cyber_audit, load_errors = _load_json(CYBER_AUDIT, "cyber audit")
    errors.extend(load_errors)
    if cyber_audit is not None:
        errors.extend(f"cyber audit: {error}" for error in validate_cyber_audit(cyber_audit))

    orchestrator = SKILLS["causal-deep-audit"]
    if orchestrator.is_file():
        text = orchestrator.read_text(encoding="utf-8")
        for dependency in SKILLS:
            if dependency == "causal-deep-audit":
                continue
            if dependency not in text:
                errors.append(f"orchestrator does not invoke dependency: {dependency}")

    return errors



def main(argv: Iterable[str] | None = None) -> int:
    del argv
    errors = validate_repository()
    if errors:
        print("Audit skill contract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(SKILLS)} causal deep-audit skills and packet schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
