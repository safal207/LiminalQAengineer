#!/usr/bin/env python3
"""Write exact-head evidence manifests and post-upload artifact receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha40(value: str, field: str) -> str:
    if not SHA40_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase 40-character SHA")
    return value


def require_sha256(value: str, field: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256 digest")
    return value.removeprefix("sha256:")


def read_rfc3339(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def collect_files(output_dir: Path, excluded: set[Path]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.resolve() in excluded:
            continue
        files.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return files


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def manifest_command(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / args.manifest_name

    expected_sha = require_sha40(args.expected_sha, "expected_sha")
    initial_sha = require_sha40(args.initial_sha, "initial_sha")
    final_sha = require_sha40(args.final_sha, "final_sha")
    workflow_sha = require_sha40(args.workflow_sha, "workflow_sha")
    if not expected_sha == initial_sha == final_sha:
        raise ValueError("expected_sha, initial_sha, and final_sha must match")

    started_at = read_rfc3339(args.started_at, "started_at")
    completed_at = read_rfc3339(args.completed_at, "completed_at")
    if completed_at < started_at:
        raise ValueError("completed_at must not precede started_at")

    files = collect_files(output_dir, {manifest_path.resolve()})
    payload = {
        "schema_version": "liminalqa-exact-head-evidence-manifest-v1",
        "audit": {
            "name": args.audit_name,
            "mode": "advisory-read-only",
            "target": args.target,
            "execution_status": args.execution_status,
        },
        "source_identity": {
            "repository": args.repository,
            "expected_sha": expected_sha,
            "initial_sha": initial_sha,
            "final_sha": final_sha,
            "workflow_sha": workflow_sha,
            "head_stable": True,
            "initial_worktree_clean": True,
            "final_worktree_clean": True,
        },
        "run_identity": {
            "event_name": args.event_name,
            "git_ref": args.git_ref,
            "head_ref": args.head_ref or None,
            "workflow_ref": args.workflow_ref,
            "run_id": str(args.run_id),
            "run_attempt": str(args.run_attempt),
            "artifact_name": args.artifact_name,
        },
        "collection": {
            "started_at": started_at,
            "completed_at": completed_at,
            "file_count": len(files),
        },
        "files": files,
        "authority": {
            "allowed": ["public passive observation", "read-only evidence capture"],
            "prohibited": [
                "authentication",
                "form submission",
                "portfolio access",
                "order entry",
                "financial operation",
                "fuzzing",
                "load testing",
                "deployment",
            ],
        },
    }
    write_json(manifest_path, payload)


def receipt_command(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_name = manifest["run_identity"]["artifact_name"]
    if args.artifact_name != expected_name:
        raise ValueError("artifact_name does not match manifest")
    if str(args.run_id) != str(manifest["run_identity"]["run_id"]):
        raise ValueError("run_id does not match manifest")
    if str(args.run_attempt) != str(manifest["run_identity"]["run_attempt"]):
        raise ValueError("run_attempt does not match manifest")

    receipt = {
        "schema_version": "liminalqa-artifact-receipt-v1",
        "manifest": {
            "path": manifest_path.name,
            "sha256": sha256_file(manifest_path),
        },
        "artifact": {
            "name": args.artifact_name,
            "id": str(args.artifact_id),
            "url": args.artifact_url,
            "sha256": require_sha256(args.artifact_digest, "artifact_digest"),
        },
        "run_identity": {
            "run_id": str(args.run_id),
            "run_attempt": str(args.run_attempt),
        },
    }
    write_json(Path(args.output).resolve(), receipt)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--output-dir", required=True)
    manifest.add_argument("--manifest-name", default="manifest.json")
    manifest.add_argument("--audit-name", required=True)
    manifest.add_argument("--target", required=True)
    manifest.add_argument("--repository", required=True)
    manifest.add_argument("--expected-sha", required=True)
    manifest.add_argument("--initial-sha", required=True)
    manifest.add_argument("--final-sha", required=True)
    manifest.add_argument("--workflow-sha", required=True)
    manifest.add_argument("--event-name", required=True)
    manifest.add_argument("--git-ref", required=True)
    manifest.add_argument("--head-ref", default="")
    manifest.add_argument("--workflow-ref", required=True)
    manifest.add_argument("--run-id", required=True)
    manifest.add_argument("--run-attempt", required=True)
    manifest.add_argument("--artifact-name", required=True)
    manifest.add_argument("--started-at", required=True)
    manifest.add_argument("--completed-at", required=True)
    manifest.add_argument("--execution-status", required=True)
    manifest.set_defaults(func=manifest_command)

    receipt = subparsers.add_parser("receipt")
    receipt.add_argument("--manifest", required=True)
    receipt.add_argument("--output", required=True)
    receipt.add_argument("--artifact-name", required=True)
    receipt.add_argument("--artifact-id", required=True)
    receipt.add_argument("--artifact-url", required=True)
    receipt.add_argument("--artifact-digest", required=True)
    receipt.add_argument("--run-id", required=True)
    receipt.add_argument("--run-attempt", required=True)
    receipt.set_defaults(func=receipt_command)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
