#!/usr/bin/env python3
"""Export deterministic Lotus Decision Packet observations as LiminalDB audit events."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PACKET_SCHEMA = "liminalqa-lotus-decision-packet-v0.1"
EVENT_SCHEMA = "liminaldb-lotus-memory-event-v0.1"
LIMINALDB_REPOSITORY = "safal207/LiminalDB"
LIMINALDB_COMMIT = "75ef9f7f403a34c60aa2ceba4cb3c97870d73e77"
LIMINALDB_CONTRACT_PATH = "sdk/ts/src/protocol-types.ts"
LIMINALDB_CONTRACT_BLOB_SHA = "fd733971aaae089df770062bcf7f2c2d6d19ca1d"
AUTHORITY_GRANTS = ("ownership", "approval", "execution", "delivery", "deployment", "merge")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


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


def validate_observed_at(value: str) -> str:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include an explicit timezone")
    return value


def validate_authority(authority: Any) -> dict[str, Any]:
    if not isinstance(authority, dict) or authority.get("mode") != "audit_only":
        raise ValueError("authority.mode must be audit_only")
    for grant in AUTHORITY_GRANTS:
        if authority.get(grant) is not False:
            raise ValueError(f"authority.{grant} must be false")
    return authority


def validate_packet(packet: dict[str, Any]) -> None:
    if packet.get("schema_version") != PACKET_SCHEMA:
        raise ValueError("unsupported Lotus decision packet schema")
    for key in ("packet_id", "repository", "source_branch", "packet_sha256"):
        require_string(packet, key, "packet")
    validate_authority(packet.get("authority"))
    findings = packet.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ValueError("packet.findings must be a non-empty list")
    ids: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("every packet finding must be an object")
        ids.append(require_string(finding, "finding_id", "finding"))
        require_string(finding, "packet_sha256", finding["finding_id"])
        for section in ("judgment", "causal_memory", "user_control", "decision", "evidence", "authority"):
            if not isinstance(finding.get(section), dict):
                raise ValueError(f"{finding['finding_id']}.{section} must be an object")
        validate_authority(finding["authority"])
    if len(ids) != len(set(ids)):
        raise ValueError("finding ids must be unique")


def build_event(
    packet: dict[str, Any],
    finding: dict[str, Any],
    observed_at: str,
    source_commit: str,
) -> dict[str, Any]:
    observed_at = validate_observed_at(observed_at)
    if len(source_commit) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit.lower()):
        raise ValueError("source_commit must be a 40-character hexadecimal commit SHA")

    causal = finding["causal_memory"]
    decision = finding["decision"]
    judgment = finding["judgment"]
    control = finding["user_control"]
    evidence = finding["evidence"]
    canonical_id = require_string(causal, "canonical_id", finding["finding_id"])

    identity = {
        "packet_sha256": packet["packet_sha256"],
        "finding_sha256": finding["packet_sha256"],
        "canonical_id": canonical_id,
        "observed_at": observed_at,
        "source_commit": source_commit,
    }
    event_id = f"lotus-{sha256_json(identity)[:32]}"
    event = {
        "id": event_id,
        "ts": observed_at,
        "kind": "audit",
        "actor": "liminalqa-lotus",
        "action": "lotus.finding.observed",
        "details": {
            "schema_version": EVENT_SCHEMA,
            "source": {
                "repository": packet["repository"],
                "branch": packet["source_branch"],
                "commit": source_commit,
                "packet_id": packet["packet_id"],
                "packet_sha256": packet["packet_sha256"],
                "finding_sha256": finding["packet_sha256"],
            },
            "finding": {
                "finding_id": finding["finding_id"],
                "canonical_id": canonical_id,
                "domain": finding.get("domain"),
                "surface": finding.get("surface"),
                "decision_status": decision.get("status"),
                "severity": decision.get("severity"),
                "confidence": decision.get("confidence"),
                "pythia_verdict": judgment.get("verdict"),
                "cml_status": causal.get("status"),
                "cml_recurrence": causal.get("recurrence"),
                "durable_memory": causal.get("durable_memory") is True,
                "ls_risk": control.get("risk"),
            },
            "evidence": {
                "state": evidence.get("state"),
                "source_path": evidence.get("source_path"),
                "bounded": evidence.get("bounded") is True,
                "replayable": evidence.get("replayable") is True,
            },
            "authority": packet["authority"],
            "adapter": {
                "repository": LIMINALDB_REPOSITORY,
                "commit": LIMINALDB_COMMIT,
                "contract_path": LIMINALDB_CONTRACT_PATH,
                "contract_blob_sha": LIMINALDB_CONTRACT_BLOB_SHA,
                "event_contract": "AuditEvent",
                "write_mode": "artifact_only",
            },
        },
    }
    event["details"]["event_sha256"] = sha256_json(event)
    return event


def export_events(packet: dict[str, Any], observed_at: str, source_commit: str) -> list[dict[str, Any]]:
    validate_packet(packet)
    events = [build_event(packet, finding, observed_at, source_commit) for finding in packet["findings"]]
    events.sort(key=lambda event: (event["details"]["finding"]["finding_id"], event["id"]))
    return events


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        if event.get("kind") != "audit" or event.get("action") != "lotus.finding.observed":
            raise ValueError(f"{path}:{line_number} is not a Lotus AuditEvent")
        if event.get("details", {}).get("schema_version") != EVENT_SCHEMA:
            raise ValueError(f"{path}:{line_number} has unsupported event schema")
        validate_authority(event.get("details", {}).get("authority"))
        details = event.get("details", {})
        recorded_hash = details.get("event_sha256")
        if not isinstance(recorded_hash, str):
            raise ValueError(f"{path}:{line_number} is missing event_sha256")
        unhashed = json.loads(json.dumps(event))
        unhashed["details"].pop("event_sha256", None)
        if sha256_json(unhashed) != recorded_hash:
            raise ValueError(f"{path}:{line_number} event_sha256 mismatch")
        events.append(event)
    return events


def write_jsonl(path: Path, events: Iterable[dict[str, Any]], append: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = {event["id"] for event in parse_jsonl(path)} if append else set()
    pending = [event for event in events if event["id"] not in existing_ids]
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for event in pending:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return len(pending)


def event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("ts", "")), str(event.get("id", "")))


def history(events: Iterable[dict[str, Any]], canonical_id: str | None, finding_id: str | None) -> dict[str, Any]:
    if not canonical_id and not finding_id:
        raise ValueError("history requires canonical_id or finding_id")
    selected = []
    for event in events:
        finding = event["details"]["finding"]
        if canonical_id and finding.get("canonical_id") != canonical_id:
            continue
        if finding_id and finding.get("finding_id") != finding_id:
            continue
        selected.append(event)
    selected.sort(key=event_sort_key)
    return {
        "schema_version": "liminaldb-lotus-history-v0.1",
        "canonical_id": canonical_id,
        "finding_id": finding_id,
        "observation_count": len(selected),
        "observations": selected,
    }


def classify_transition(previous: dict[str, Any], current: dict[str, Any]) -> str:
    prev_details = previous["details"]
    curr_details = current["details"]
    prev_finding = prev_details["finding"]
    curr_finding = curr_details["finding"]
    prev_status = prev_finding.get("decision_status")
    curr_status = curr_finding.get("decision_status")

    if previous["id"] == current["id"]:
        return "DUPLICATE_OBSERVATION"
    if prev_status == "CONFIRMED" and curr_status == "CONFIRMED":
        if prev_details["source"].get("finding_sha256") == curr_details["source"].get("finding_sha256"):
            return "STILL_PRESENT"
        return "STILL_PRESENT_IN_CHANGED_FORM"
    if prev_status == "NEEDS_EVIDENCE" and curr_status == "CONFIRMED":
        return "NOW_CONFIRMED"
    if prev_status == "BLOCKED" and curr_status == "CONFIRMED":
        return "REOPENED_CONFIRMED"
    if prev_status == "CONFIRMED" and curr_status == "NEEDS_EVIDENCE":
        return "EVIDENCE_REGRESSED"
    if prev_status == "CONFIRMED" and curr_status == "BLOCKED":
        return "CLAIM_REJECTED"
    if prev_status == curr_status:
        return "UNCHANGED_DECISION"
    return f"{prev_status}_TO_{curr_status}"


def compare(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        canonical_id = event["details"]["finding"]["canonical_id"]
        grouped.setdefault(canonical_id, []).append(event)
    transitions = []
    for canonical_id, observations in sorted(grouped.items()):
        observations.sort(key=event_sort_key)
        for previous, current in zip(observations, observations[1:]):
            transitions.append(
                {
                    "canonical_id": canonical_id,
                    "from_event_id": previous["id"],
                    "to_event_id": current["id"],
                    "from_ts": previous["ts"],
                    "to_ts": current["ts"],
                    "transition": classify_transition(previous, current),
                }
            )
    return {
        "schema_version": "liminaldb-lotus-compare-v0.1",
        "event_count": sum(len(values) for values in grouped.values()),
        "canonical_finding_count": len(grouped),
        "transition_count": len(transitions),
        "transitions": transitions,
    }


def write_json(path: Path | None, value: dict[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(rendered, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--packet", type=Path, required=True)
    export_parser.add_argument("--observed-at", required=True)
    export_parser.add_argument("--source-commit", required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--append", action="store_true")

    history_parser = subparsers.add_parser("history")
    history_parser.add_argument("--events", type=Path, required=True)
    history_filter = history_parser.add_mutually_exclusive_group(required=True)
    history_filter.add_argument("--canonical-id")
    history_filter.add_argument("--finding-id")
    history_parser.add_argument("--output", type=Path)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--events", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path)

    args = parser.parse_args()
    if args.command == "export":
        packet = load_json(args.packet)
        events = export_events(packet, args.observed_at, args.source_commit.lower())
        written = write_jsonl(args.output, events, append=args.append)
        print(json.dumps({"event_count": len(events), "written": written, "output": str(args.output)}, sort_keys=True))
    elif args.command == "history":
        value = history(parse_jsonl(args.events), args.canonical_id, args.finding_id)
        write_json(args.output, value)
    else:
        value = compare(parse_jsonl(args.events))
        write_json(args.output, value)


if __name__ == "__main__":
    main()
