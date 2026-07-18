#!/usr/bin/env python3
"""Merge multiple Lotus findings documents without weakening provenance or authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "liminalqa-lotus-findings-v0.1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def require_string(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def merge_documents(
    documents: list[dict[str, Any]],
    *,
    packet_id: str,
    source_branch: str,
    scope: str,
) -> dict[str, Any]:
    if not documents:
        raise ValueError("at least one findings document is required")

    repository: str | None = None
    findings: list[dict[str, Any]] = []
    source_packets: list[dict[str, str]] = []

    for index, document in enumerate(documents):
        context = f"documents[{index}]"
        if document.get("schema_version") != SCHEMA:
            raise ValueError(f"{context} has unsupported schema")
        current_repository = require_string(document, "repository", context)
        if repository is None:
            repository = current_repository
        elif current_repository != repository:
            raise ValueError("all findings documents must use the same repository")

        source_packets.append(
            {
                "packet_id": require_string(document, "packet_id", context),
                "source_branch": require_string(document, "source_branch", context),
                "scope": require_string(document, "scope", context),
            }
        )
        current_findings = document.get("findings")
        if not isinstance(current_findings, list) or not current_findings:
            raise ValueError(f"{context}.findings must be a non-empty list")
        for finding in current_findings:
            if not isinstance(finding, dict):
                raise ValueError(f"{context}.findings must contain objects")
            require_string(finding, "id", f"{context}.finding")
            findings.append(finding)

    ids = [finding["id"] for finding in findings]
    if len(ids) != len(set(ids)):
        duplicates = sorted({fid for fid in ids if ids.count(fid) > 1})
        raise ValueError(f"duplicate finding ids: {duplicates}")

    findings.sort(key=lambda item: item["id"])
    source_packets.sort(key=lambda item: (item["packet_id"], item["source_branch"]))

    return {
        "schema_version": SCHEMA,
        "packet_id": packet_id,
        "repository": repository,
        "source_branch": source_branch,
        "scope": scope,
        "source_packets": source_packets,
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--packet-id", required=True)
    parser.add_argument("--source-branch", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    documents = [load_json(path) for path in args.input]
    merged = merge_documents(
        documents,
        packet_id=args.packet_id,
        source_branch=args.source_branch,
        scope=args.scope,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "packet_id": merged["packet_id"],
        "source_packet_count": len(merged["source_packets"]),
        "finding_count": len(merged["findings"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
