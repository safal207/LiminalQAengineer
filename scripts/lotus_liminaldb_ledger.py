#!/usr/bin/env python3
"""Create and verify a deterministic LiminalDB-compatible ledger from a Lotus packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

EVENT_ORDER = (
    ("evidence_observed", "evidence"),
    ("pythia_judged", "judgment"),
    ("cml_memory_proposed", "causal_memory"),
    ("ls_control_assessed", "user_control"),
    ("lotus_decided", "decision"),
)

FALSE_AUTHORITY_GRANTS = ("ownership", "approval", "execution", "delivery", "deployment", "merge")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_authority(authority: dict[str, Any]) -> None:
    if authority.get("mode") != "audit_only":
        raise ValueError("authority.mode must remain audit_only")
    for grant in FALSE_AUTHORITY_GRANTS:
        if authority.get(grant) is not False:
            raise ValueError(f"authority.{grant} must be false")


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != "liminalqa-lotus-liminaldb-bridge-v0.1":
        raise ValueError("unsupported LiminalDB bridge contract")
    source = contract.get("liminaldb_source")
    if not isinstance(source, dict):
        raise ValueError("liminaldb_source must be an object")
    for key in ("repository", "commit", "path", "blob_sha", "rule"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise ValueError(f"liminaldb_source.{key} must be a non-empty string")
    validate_authority(contract.get("authority") or {})
    event_types = contract.get("event_types")
    if event_types != [name for name, _ in EVENT_ORDER]:
        raise ValueError("event_types must match the deterministic bridge order")


def validate_packet(packet: dict[str, Any]) -> None:
    if packet.get("schema_version") != "liminalqa-lotus-decision-packet-v0.1":
        raise ValueError("unsupported Lotus decision packet")
    findings = packet.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ValueError("packet.findings must be a non-empty list")
    validate_authority(packet.get("authority") or {})
    expected_hash = packet.get("packet_sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("packet.packet_sha256 must be a SHA-256 hex string")
    unhashed = dict(packet)
    unhashed.pop("packet_sha256", None)
    if sha256_json(unhashed) != expected_hash:
        raise ValueError("packet_sha256 does not match canonical packet content")
    ids: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("every packet finding must be an object")
        fid = finding.get("finding_id")
        if not isinstance(fid, str) or not fid:
            raise ValueError("every finding requires finding_id")
        ids.append(fid)
        for _, section in EVENT_ORDER:
            if not isinstance(finding.get(section), dict):
                raise ValueError(f"{fid}.{section} must be an object")
    if len(ids) != len(set(ids)):
        raise ValueError("finding_id values must be unique")


def event_body(
    *,
    sequence: int,
    event_type: str,
    finding: dict[str, Any],
    section: str,
    packet: dict[str, Any],
    previous_event_sha256: str | None,
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "liminalqa-lotus-ledger-event-v0.1",
        "sequence": sequence,
        "event_type": event_type,
        "finding_id": finding["finding_id"],
        "canonical_id": finding["causal_memory"]["canonical_id"],
        "packet_id": packet["packet_id"],
        "source_packet_sha256": packet["packet_sha256"],
        "previous_event_sha256": previous_event_sha256,
        "payload": finding[section],
        "authority": contract["authority"],
    }


def build_ledger(contract: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    validate_contract(contract)
    validate_packet(packet)
    events: list[dict[str, Any]] = []
    previous: str | None = None
    sequence = 1
    for finding in sorted(packet["findings"], key=lambda item: item["finding_id"]):
        for event_type, section in EVENT_ORDER:
            body = event_body(
                sequence=sequence,
                event_type=event_type,
                finding=finding,
                section=section,
                packet=packet,
                previous_event_sha256=previous,
                contract=contract,
            )
            event = dict(body)
            event["event_sha256"] = sha256_json(body)
            events.append(event)
            previous = event["event_sha256"]
            sequence += 1
    return events


def verify_ledger(events: Iterable[dict[str, Any]], contract: dict[str, Any], packet: dict[str, Any]) -> None:
    validate_contract(contract)
    validate_packet(packet)
    event_list = list(events)
    expected_count = len(packet["findings"]) * len(EVENT_ORDER)
    if len(event_list) != expected_count:
        raise ValueError(f"ledger event count must be {expected_count}, got {len(event_list)}")
    previous: str | None = None
    for index, event in enumerate(event_list, start=1):
        if event.get("sequence") != index:
            raise ValueError(f"ledger sequence break at event {index}")
        if event.get("previous_event_sha256") != previous:
            raise ValueError(f"ledger previous hash mismatch at event {index}")
        if event.get("source_packet_sha256") != packet["packet_sha256"]:
            raise ValueError(f"ledger packet hash mismatch at event {index}")
        if event.get("authority") != contract["authority"]:
            raise ValueError(f"ledger authority drift at event {index}")
        body = dict(event)
        observed = body.pop("event_sha256", None)
        expected = sha256_json(body)
        if observed != expected:
            raise ValueError(f"ledger event hash mismatch at event {index}")
        previous = observed


def build_snapshot(events: list[dict[str, Any]], contract: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    verify_ledger(events, contract, packet)
    states: dict[str, dict[str, Any]] = {}
    event_sections = dict(EVENT_ORDER)
    for event in events:
        state = states.setdefault(
            event["finding_id"],
            {
                "canonical_id": event["canonical_id"],
                "evidence": None,
                "judgment": None,
                "causal_memory": None,
                "user_control": None,
                "decision": None,
                "last_event_sha256": None,
            },
        )
        section = event_sections[event["event_type"]]
        state[section] = event["payload"]
        state["last_event_sha256"] = event["event_sha256"]
    snapshot = {
        "schema_version": "liminalqa-lotus-ledger-snapshot-v0.1",
        "packet_id": packet["packet_id"],
        "source_packet_sha256": packet["packet_sha256"],
        "liminaldb_source": contract["liminaldb_source"],
        "event_count": len(events),
        "finding_count": len(states),
        "ledger_head_sha256": events[-1]["event_sha256"],
        "findings": dict(sorted(states.items())),
        "authority": contract["authority"],
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    return snapshot


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{lineno} must contain a JSON object")
        events.append(value)
    return events


def write_outputs(output_dir: Path, events: list[dict[str, Any]], snapshot: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "lotus-ledger.jsonl"
    snapshot_path = output_dir / "lotus-ledger-snapshot.json"
    manifest_path = output_dir / "manifest.sha256"
    ledger_path.write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(
        f"{hashlib.sha256(ledger_path.read_bytes()).hexdigest()}  {ledger_path.name}\n"
        f"{hashlib.sha256(snapshot_path.read_bytes()).hexdigest()}  {snapshot_path.name}\n",
        encoding="utf-8",
    )


def generate(args: argparse.Namespace) -> None:
    contract = load_json(args.contract)
    packet = load_json(args.packet)
    events = build_ledger(contract, packet)
    snapshot = build_snapshot(events, contract, packet)
    write_outputs(args.output_dir, events, snapshot)
    print(json.dumps({
        "event_count": len(events),
        "finding_count": snapshot["finding_count"],
        "ledger_head_sha256": snapshot["ledger_head_sha256"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
    }, sort_keys=True))


def verify(args: argparse.Namespace) -> None:
    contract = load_json(args.contract)
    packet = load_json(args.packet)
    events = read_jsonl(args.ledger)
    verify_ledger(events, contract, packet)
    snapshot = load_json(args.snapshot)
    expected_snapshot = build_snapshot(events, contract, packet)
    if snapshot != expected_snapshot:
        raise ValueError("snapshot does not match replayed ledger")
    print(json.dumps({
        "verified": True,
        "event_count": len(events),
        "ledger_head_sha256": expected_snapshot["ledger_head_sha256"],
        "snapshot_sha256": expected_snapshot["snapshot_sha256"],
    }, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--contract", type=Path, required=True)
    common.add_argument("--packet", type=Path, required=True)

    generate_parser = subparsers.add_parser("generate", parents=[common])
    generate_parser.add_argument("--output-dir", type=Path, required=True)
    generate_parser.set_defaults(func=generate)

    verify_parser = subparsers.add_parser("verify", parents=[common])
    verify_parser.add_argument("--ledger", type=Path, required=True)
    verify_parser.add_argument("--snapshot", type=Path, required=True)
    verify_parser.set_defaults(func=verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
