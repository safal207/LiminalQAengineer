#!/usr/bin/env python3
"""Write an immutable manifest for the local cyber-causal guardrail replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


REPOSITORY_FILES = (
    ".github/workflows/ci.yml",
    "scripts/cyber_causal_guardrail_replay.py",
    "scripts/write_cyber_guardrail_manifest.py",
    "scripts/verify_cyber_guardrail_ci.py",
    "tests/test_cyber_causal_guardrail_replay.py",
    "liminalqa-core/tests/cyber_causal_guardrail_replay.rs",
    "audits/security/cyber-causal-guardrail-replay-v0-2.json",
    "docs/audits/CYBER_CAUSAL_GUARDRAIL_REPLAY_V0_2.md",
    "docs/audits/CYBER_CAUSAL_GUARDRAIL_EVIDENCE_CONTRACT.md",
)
EVIDENCE_FILES = ("result.json", "result-replay.json")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path, display_path: str) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": display_path,
        "size": len(data),
        "sha256": sha256_bytes(data),
    }


def build_manifest(
    *,
    repository_root: Path,
    evidence_dir: Path,
    expected_sha: str,
    initial_sha: str,
    final_sha: str,
    repository: str,
    run_id: str,
    run_attempt: str,
) -> dict[str, object]:
    for name, value in {
        "expected_sha": expected_sha,
        "initial_sha": initial_sha,
        "final_sha": final_sha,
    }.items():
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError(f"{name} must be an exact lowercase 40-character SHA")
    if not (expected_sha == initial_sha == final_sha):
        raise ValueError("expected, initial, and final source identity must match")

    result_path = evidence_dir / "result.json"
    replay_path = evidence_dir / "result-replay.json"
    result_bytes = result_path.read_bytes()
    replay_bytes = replay_path.read_bytes()
    if result_bytes != replay_bytes:
        raise ValueError("replay outputs are not byte-identical")

    result = json.loads(result_bytes)
    if result.get("source_sha") != expected_sha:
        raise ValueError("result source_sha does not match exact audited head")
    if result.get("verdict") != (
        "CONFIRMED_LOCAL_MECHANISM_REPRODUCTION_AND_GUARDRAIL_PASS"
    ):
        raise ValueError("result verdict is not the required local replay verdict")
    for flag in ("network_access", "credential_use", "external_mutation"):
        if result.get(flag) is not False:
            raise ValueError(f"unsafe result flag: {flag}")
    if result.get("external_product_claim") != "NONE":
        raise ValueError("external product claim boundary was expanded")

    files: list[dict[str, object]] = []
    for relative in REPOSITORY_FILES:
        files.append(file_record(repository_root / relative, relative))
    for name in EVIDENCE_FILES:
        files.append(file_record(evidence_dir / name, name))

    return {
        "schema_version": "1.0",
        "repository": repository,
        "expected_sha": expected_sha,
        "initial_sha": initial_sha,
        "final_sha": final_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "authority": "LOCAL_DETERMINISTIC_SIMULATION_ONLY",
        "network_access": False,
        "credential_use": False,
        "external_mutation": False,
        "external_product_claim": "NONE",
        "byte_identical_replay": True,
        "result_sha256": sha256_bytes(result_bytes),
        "file_count": len(files),
        "files": files,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--initial-sha", required=True)
    parser.add_argument("--final-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_manifest(
        repository_root=args.repository_root.resolve(),
        evidence_dir=args.evidence_dir.resolve(),
        expected_sha=args.expected_sha,
        initial_sha=args.initial_sha,
        final_sha=args.final_sha,
        repository=os.environ.get("GITHUB_REPOSITORY", "local"),
        run_id=os.environ.get("GITHUB_RUN_ID", "local"),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
