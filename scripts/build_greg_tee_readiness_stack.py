#!/usr/bin/env python3
"""Build the LPI/CaPU/T-Trace/TTM/SDP/DRP readiness evidence packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

READY_VERDICT = "READY_TO_NOTIFY_READINESS_BARRIER_SUPPORTED_CAUSE_NOT_EXCLUSIVE"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def iso_from_ns(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def find_platform_results(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, load(path)) for path in sorted(root.rglob("greg-readiness-platform-result.json"))]


def bucket(result: dict[str, Any], scenario: str, pty: bool, mode: str) -> dict[str, Any]:
    return result["coordinates"][f"{scenario}|pty={int(pty)}|{mode}"]


def sum_failures(result: dict[str, Any], *, pty: bool, mode: str) -> tuple[int, int, int]:
    selected = [bucket(result, scenario, pty, mode) for scenario in ("issue", "fd")]
    return (
        sum(item["failures"] for item in selected),
        sum(item["total"] for item in selected),
        sum(item["gate_failures"] for item in selected),
    )


def build_profiles(results: list[dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for result in results:
        system = result["platform"]["system"]
        profile: dict[str, Any] = {}
        for pty_value, pty_name in ((False, "nonpty"), (True, "pty")):
            for mode in (
                "current",
                "sleep100",
                "file_exists",
                "supervisor_ack",
                "supervisor_ack_safe_close",
            ):
                failures, total, gate_failures = sum_failures(result, pty=pty_value, mode=mode)
                profile[f"{pty_name}_{mode}"] = {
                    "failures": failures,
                    "total": total,
                    "gate_failures": gate_failures,
                }
        profiles[system] = profile
    return profiles


def build_ttrace(results: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for result in results:
        for entry_index, entry in enumerate(result["entries"], start=1):
            child = entry.get("result")
            if not child:
                continue
            events = child["events"]
            thread_id = child["trace_id"]
            sense = events[0]
            gate_event = next(
                (
                    item
                    for item in events
                    if item["name"]
                    in {"COMMIT_CAPU_WRITE_GATE_OPENED", "COMMIT_CAPU_WRITE_GATE_REJECTED"}
                ),
                events[min(1, len(events) - 1)],
            )
            final = events[-1]
            base = f'{result["platform"]["system"].lower()}-{entry_index:04d}'
            records.extend(
                [
                    {
                        "id": f"{base}-sense",
                        "type": "sense",
                        "ts": iso_from_ns(sense["wall_time_ns"]),
                        "thread_id": thread_id,
                        "input": "tee-readiness-trajectory",
                        "coordinate": child["coordinate"],
                    },
                    {
                        "id": f"{base}-transition",
                        "type": "transition",
                        "ts": iso_from_ns(gate_event["wall_time_ns"]),
                        "thread_id": thread_id,
                        "from": "spawned",
                        "to": "flow_allowed" if child["gate"].get("passed", True) else "flow_rejected",
                        "gate": child["gate"],
                    },
                    {
                        "id": f"{base}-commit",
                        "type": "commit",
                        "ts": iso_from_ns(final["wall_time_ns"]),
                        "thread_id": thread_id,
                        "confidence": 1.0,
                        "passed": child["verification"]["passed"],
                    },
                ]
            )
    path = out / "ttrace" / "readiness.ttrace.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    return {"records": len(records), "threads": len(records) // 3, "path": str(path)}


def build_ttm(results: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    previous = "0" * 64
    for result in sorted(results, key=lambda item: item["platform"]["system"]):
        for entry in result["entries"]:
            child = entry.get("result")
            if not child:
                continue
            for raw in child["events"]:
                body = {
                    "thread_id": child["trace_id"],
                    "transition_id": f'{child["trace_id"]}:{raw["sequence"]}',
                    "ts": iso_from_ns(raw["wall_time_ns"]),
                    "from_state_ref": raw["details"].get("from"),
                    "to_state_ref": raw["name"],
                    "admissibility": "observed",
                    "confidence": 1.0,
                    "lane": f'{result["platform"]["system"]}:{child["coordinate"]["mode"]}',
                    "metadata": {
                        "coordinate": child["coordinate"],
                        "details": raw["details"],
                        "monotonic_ns": raw["monotonic_ns"],
                    },
                    "previous_hash": previous,
                }
                digest = sha256_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
                body["seal"] = digest
                previous = digest
                records.append(body)
    path = out / "ttm-db" / "ground-truth.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")

    replay_previous = "0" * 64
    errors = []
    for index, record in enumerate(records):
        candidate = dict(record)
        seal = candidate.pop("seal")
        if candidate["previous_hash"] != replay_previous:
            errors.append({"index": index, "reason": "previous_hash_mismatch"})
        expected = sha256_bytes(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode())
        if seal != expected:
            errors.append({"index": index, "reason": "seal_mismatch"})
        replay_previous = seal
    report = {
        "records": len(records),
        "errors": errors,
        "passed": bool(records) and not errors,
        "chain_head": previous,
        "boundary": "Append-only adapter; no production TTM DB service claim.",
    }
    write_json(out / "ttm-db" / "replay-report.json", report)
    return report


def hypothesis(score: float, evidence: list[str], status: str) -> dict[str, Any]:
    return {"score": round(score, 3), "status": status, "evidence": evidence}


def build_sdp(profiles: dict[str, Any], out: Path) -> dict[str, Any]:
    systems = sorted(profiles)
    current_fail = sum(profiles[s]["pty_current"]["failures"] for s in systems)
    file_fail = sum(profiles[s]["pty_file_exists"]["failures"] for s in systems)
    ack_fail = sum(profiles[s]["pty_supervisor_ack"]["failures"] for s in systems)
    safe_fail = sum(profiles[s]["pty_supervisor_ack_safe_close"]["failures"] for s in systems)
    sleep_fail = sum(profiles[s]["pty_sleep100"]["failures"] for s in systems)

    values = {
        "H1_PRE_OUTPUT_OPEN_WINDOW": hypothesis(
            1.0 if current_fail > 0 and file_fail == 0 else 0.2,
            [f"current_pty_failures={current_fail}", f"file_exists_failures={file_fail}"],
            "supported" if current_fail > 0 and file_fail == 0 else "not_selected",
        ),
        "H2_SUPERVISOR_ACK_REQUIRED": hypothesis(
            1.0 if file_fail > 0 and ack_fail == 0 else (0.7 if ack_fail == 0 and current_fail > 0 else 0.1),
            [f"file_exists_failures={file_fail}", f"supervisor_ack_failures={ack_fail}"],
            "supported" if ack_fail == 0 and current_fail > 0 else "not_selected",
        ),
        "H3_DELAY_ONLY_EFFECT": hypothesis(
            0.6 if sleep_fail == 0 and ack_fail > 0 else 0.1,
            [f"sleep100_failures={sleep_fail}", f"supervisor_ack_failures={ack_fail}"],
            "candidate" if sleep_fail == 0 and ack_fail > 0 else "not_selected",
        ),
        "H4_SHUTDOWN_CONTRIBUTES": hypothesis(
            0.8 if safe_fail < ack_fail else 0.2,
            [f"supervisor_ack_failures={ack_fail}", f"ack_safe_close_failures={safe_fail}"],
            "candidate" if safe_fail < ack_fail else "not_selected",
        ),
    }
    selected = max(values.items(), key=lambda item: item[1]["score"])[0]
    report = {
        "schema_version": "liminalqa-sdp-readiness-v1",
        "levels": {
            "macro": "tee-output drops immediate PTY writes",
            "meso": ["PTY setup", "parent-lifetime", "system tee", "shutdown"],
            "micro": ["file creation", "child liveness", "supervisor acknowledgement", "EOF drain"],
            "pico": ["spawn timestamp", "target-file existence timestamp", "ack timestamp", "first write timestamp", "close timestamp"],
        },
        "hypotheses": values,
        "selected_hypothesis": selected,
        "boundary": "Evidence collapse is deterministic and advisory; it does not establish a sole root cause.",
    }
    write_json(out / "sdp" / "hypothesis-collapse.json", report)
    return report


def build_drp(verdict: str, profiles: dict[str, Any], out: Path) -> list[dict[str, Any]]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    records = [
        {
            "record_id": "greg-tee-decision-shutdown-001",
            "timestamp": "2026-07-20T20:29:17Z",
            "context": "The first cross-platform matrix reproduced PTY timing loss, while a shutdown-order counterfactual remained non-clean.",
            "decision": "Do not claim SIGINT or shutdown ordering as the sole root cause.",
            "options": ["Claim shutdown as sole cause", "Keep root cause unresolved", "Reject the symptom"],
            "status": "complete",
            "rationale": "The safe-close counterfactual still failed in multiple PTY coordinates.",
            "tags": ["greg", "tee-output", "pty", "shutdown"],
        },
        {
            "record_id": "greg-tee-decision-readiness-002",
            "timestamp": now,
            "context": "A new matrix compares immediate writes, fixed delay, output-file observation, supervisor acknowledgement, and supervisor acknowledgement with safe close.",
            "decision": (
                "Treat readiness barrier evidence as causally supportive but not exclusive."
                if verdict == READY_VERDICT
                else "Keep the readiness hypothesis unresolved."
            ),
            "options": ["Promote readiness as sole root cause", "Treat readiness as supported but non-exclusive", "Keep readiness unresolved"],
            "status": "superseded",
            "supersedes_record_id": "greg-tee-decision-shutdown-001",
            "parent_record_ids": ["greg-tee-decision-shutdown-001"],
            "rationale": verdict,
            "impact": 1 if verdict == READY_VERDICT else 0,
            "tags": ["greg", "tee-output", "readiness", "handshake"],
            "metadata": {"profiles": profiles},
        },
    ]
    records[0]["child_record_ids"] = ["greg-tee-decision-readiness-002"]
    write_json(out / "drp" / "decisions.json", records)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--component-contracts", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_root = Path(args.input_root)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pairs = find_platform_results(input_root)
    results = [value for _path, value in pairs]
    profiles = build_profiles(results) if results else {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    systems = set(profiles)
    add("linux_and_macos_present", systems == {"Linux", "Darwin"}, sorted(systems))
    add(
        "platform_execution_complete",
        bool(results) and all(item["summary"]["execution_complete"] for item in results),
        [item.get("summary") for item in results],
    )

    for system, profile in profiles.items():
        add(f"{system}_current_nonpty_passes", profile["nonpty_current"]["failures"] == 0, profile["nonpty_current"])
        add(f"{system}_current_pty_reproduces", profile["pty_current"]["failures"] > 0, profile["pty_current"])
        add(f"{system}_sleep100_pty_passes", profile["pty_sleep100"]["failures"] == 0, profile["pty_sleep100"])
        add(f"{system}_supervisor_ack_gate_passes", profile["pty_supervisor_ack"]["gate_failures"] == 0, profile["pty_supervisor_ack"])

    contracts = load(Path(args.component_contracts))
    add("component_contracts_pass", contracts.get("passed") is True, contracts)

    blocking = [item for item in checks if not item["passed"]]
    ack_clean = bool(profiles) and all(profile["pty_supervisor_ack"]["failures"] == 0 for profile in profiles.values())
    current_reproduced = bool(profiles) and all(profile["pty_current"]["failures"] > 0 for profile in profiles.values())
    if blocking:
        verdict = "BLOCKED_READINESS_EVIDENCE_INCOMPLETE"
    elif ack_clean and current_reproduced:
        verdict = READY_VERDICT
    else:
        verdict = "HOLD_READINESS_BARRIER_NOT_SUFFICIENT"

    ttrace = build_ttrace(results, out)
    ttm = build_ttm(results, out)
    sdp = build_sdp(profiles, out)
    drp = build_drp(verdict, profiles, out)

    report = {
        "schema_version": "liminalqa-greg-readiness-full-stack-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform_results": [
            {"path": str(path), "sha256": sha256_file(path), "result": result}
            for path, result in pairs
        ],
        "component_contracts": contracts,
        "profiles": profiles,
        "checks": checks,
        "blocking_checks": blocking,
        "layers": {
            "lpi": {
                "model": "Hello -> Mirror -> Bind -> Seal -> Flow adapted to process startup",
                "ack_kind": "supervisor observes actual tee alive and all targets created",
                "internal_read_loop_claim": False,
            },
            "capu": {"model": "Gate -> Incubate -> Commit -> Execute", "write_before_gate": False},
            "ttrace": ttrace,
            "ttm_db": ttm,
            "sdp": sdp,
            "drp": {"records": len(drp)},
        },
        "summary": {
            "verdict": verdict,
            "symptom_status": "CONFIRMED_BY_PRIOR_MATRIX",
            "readiness_status": "SUPPORTED_NON_EXCLUSIVE" if verdict == READY_VERDICT else "UNRESOLVED",
            "sole_root_cause_status": "UNRESOLVED",
        },
        "notification_contract": {
            "permitted": verdict == READY_VERDICT,
            "comments_only": True,
            "state_changes": False,
            "may_claim_readiness_support": verdict == READY_VERDICT,
            "may_claim_readiness_as_sole_cause": False,
            "must_disclose_supervisory_not_internal_ack": True,
            "must_disclose_wrapper_process_tree_difference": True,
        },
    }
    write_json(out / "greg-readiness-full-stack-result.json", report)

    summary = [
        "# Greg tee-output readiness evidence",
        "",
        f"- verdict: **{verdict}**",
        f"- blocking checks: `{len(blocking)}`",
        f"- systems: `{', '.join(sorted(systems))}`",
        f"- T-Trace records: `{ttrace['records']}`",
        f"- TTM records: `{ttm['records']}`",
        f"- TTM replay errors: `{len(ttm['errors'])}`",
        f"- SDP selected: `{sdp['selected_hypothesis']}`",
        "",
        "The acknowledgement is supervisory: actual `tee` is alive and all target files exist.",
        "It is not an internal source-level acknowledgement from the `tee` read loop.",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")

    checksums = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksums.append(f"{sha256_file(path)}  {path.relative_to(out)}")
    (out / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "blocking": len(blocking), "profiles": profiles}, sort_keys=True))
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
