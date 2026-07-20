#!/usr/bin/env python3
"""Build post-write drain evidence, replay, hypothesis, and claim boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

READY_VERDICT = "READY_TO_NOTIFY_POSTWRITE_DRAIN_BARRIER_SUPPORTED_CAUSE_NOT_EXCLUSIVE"


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


def find_results(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, load(path)) for path in sorted(root.rglob("greg-postwrite-platform-result.json"))]


def build_profiles(results: list[dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for result in results:
        system = result["platform"]["system"]
        by_mode: dict[str, Any] = {}
        for bucket in result["coordinates"].values():
            mode = bucket["mode"]
            aggregate = by_mode.setdefault(
                mode,
                {
                    "failures": 0,
                    "total": 0,
                    "startup_gate_failures": 0,
                    "postwrite_barrier_failures": 0,
                    "scenarios": {},
                },
            )
            aggregate["failures"] += bucket["failures"]
            aggregate["total"] += bucket["total"]
            aggregate["startup_gate_failures"] += bucket["startup_gate_failures"]
            aggregate["postwrite_barrier_failures"] += bucket["postwrite_barrier_failures"]
            aggregate["scenarios"][bucket["scenario"]] = bucket
        profiles[system] = by_mode
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
            drain = next(
                item for item in events if item["name"] == "TRANSITION_POSTWRITE_BARRIER_RESOLVED"
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
                        "input": "tee-postwrite-drain-trajectory",
                        "coordinate": child["coordinate"],
                    },
                    {
                        "id": f"{base}-transition",
                        "type": "transition",
                        "ts": iso_from_ns(drain["wall_time_ns"]),
                        "thread_id": thread_id,
                        "from": "payload_dispatched",
                        "to": "close_gate_evaluated",
                        "barrier": child["postwrite_barrier"],
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
    path = out / "ttrace" / "postwrite-drain.ttrace.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    return {"records": len(records), "threads": len(records) // 3, "path": str(path)}


def build_ttm(results: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    previous = "0" * 64
    for result in sorted(results, key=lambda value: value["platform"]["system"]):
        for entry in result["entries"]:
            child = entry.get("result")
            if not child:
                continue
            for raw in child["events"]:
                body = {
                    "thread_id": child["trace_id"],
                    "transition_id": f'{child["trace_id"]}:{raw["sequence"]}',
                    "ts": iso_from_ns(raw["wall_time_ns"]),
                    "from_state_ref": None,
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
                seal = sha256_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
                body["seal"] = seal
                previous = seal
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
        if expected != seal:
            errors.append({"index": index, "reason": "seal_mismatch"})
        replay_previous = seal
    report = {
        "records": len(records),
        "errors": errors,
        "passed": bool(records) and not errors,
        "chain_head": previous,
        "boundary": "Append-only TTM adapter; no live production database claim.",
    }
    write_json(out / "ttm-db" / "replay-report.json", report)
    return report


def mode_failures(profiles: dict[str, Any], mode: str) -> int:
    return sum(platform[mode]["failures"] for platform in profiles.values())


def build_sdp(profiles: dict[str, Any], out: Path) -> dict[str, Any]:
    immediate = mode_failures(profiles, "ack_immediate")
    sleep_failures = {
        delay: mode_failures(profiles, f"ack_postwrite_{delay}ms")
        for delay in (1, 5, 10, 25)
    }
    quiescence = mode_failures(profiles, "ack_quiescence_5ms")
    output_complete = mode_failures(profiles, "ack_output_complete")
    output_complete_safe = mode_failures(profiles, "ack_output_complete_safe_close")
    direct_safe = mode_failures(profiles, "direct_ack_safe_close")
    direct_complete_safe = mode_failures(profiles, "direct_ack_output_complete_safe_close")

    hypotheses = {
        "H1_FIXED_DELAY_SUFFICIENT": {
            "score": 0.7 if all(value == 0 for value in sleep_failures.values()) else 0.1,
            "status": "candidate" if all(value == 0 for value in sleep_failures.values()) else "not_selected",
            "evidence": sleep_failures,
        },
        "H2_POSTWRITE_DRAIN_BARRIER_REQUIRED": {
            "score": 1.0 if immediate > 0 and output_complete == 0 else 0.2,
            "status": "supported" if immediate > 0 and output_complete == 0 else "not_selected",
            "evidence": {
                "immediate_failures": immediate,
                "output_complete_failures": output_complete,
                "output_complete_safe_close_failures": output_complete_safe,
            },
        },
        "H3_SIZE_QUIESCENCE_SUFFICIENT": {
            "score": 0.8 if immediate > 0 and quiescence == 0 else 0.2,
            "status": "candidate" if immediate > 0 and quiescence == 0 else "not_selected",
            "evidence": {"immediate_failures": immediate, "quiescence_failures": quiescence},
        },
        "H4_PARENT_LIFETIME_CONTRIBUTES": {
            "score": 0.7 if direct_safe < immediate else 0.2,
            "status": "candidate" if direct_safe < immediate else "not_selected",
            "evidence": {
                "parent_current_close_failures": immediate,
                "direct_safe_close_failures": direct_safe,
                "direct_complete_safe_close_failures": direct_complete_safe,
            },
        },
    }
    selected = max(hypotheses.items(), key=lambda item: item[1]["score"])[0]
    report = {
        "schema_version": "liminalqa-sdp-postwrite-drain-v1",
        "levels": {
            "macro": "tail records disappear when close follows a PTY burst",
            "meso": ["startup acknowledgement", "write burst", "reader drain", "shutdown topology"],
            "micro": ["fixed delay", "size quiescence", "observed output completion", "parent-lifetime"],
            "pico": ["last write timestamp", "last file-size change", "last expected marker observed", "close timestamp"],
        },
        "hypotheses": hypotheses,
        "selected_hypothesis": selected,
        "boundary": "Deterministic advisory collapse; no sole-root-cause claim.",
    }
    write_json(out / "sdp" / "hypothesis-collapse.json", report)
    return report


def build_drp(verdict: str, profiles: dict[str, Any], out: Path) -> list[dict[str, Any]]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    records = [
        {
            "record_id": "greg-tee-readiness-hold-001",
            "timestamp": "2026-07-20T21:20:07Z",
            "context": "Supervisor startup acknowledgement reduced failures but did not eliminate macOS fd-burst tail loss.",
            "decision": "Keep readiness as helpful but insufficient and test a post-write drain phase.",
            "options": ["Promote readiness as sole cause", "Keep readiness unresolved", "Reject the symptom"],
            "status": "complete",
            "rationale": "The exact readiness artifact retained two macOS failures after successful startup acknowledgement.",
            "tags": ["greg", "tee-output", "readiness", "drain"],
        },
        {
            "record_id": "greg-tee-postwrite-drain-002",
            "timestamp": now,
            "context": "The post-write matrix compares immediate close, bounded delays, size quiescence, observed output completion, and direct relay topology.",
            "decision": (
                "Treat a post-write drain/completion barrier as causally supportive but non-exclusive."
                if verdict == READY_VERDICT
                else "Keep the post-write drain hypothesis unresolved."
            ),
            "options": ["Promote drain as sole cause", "Treat drain as supported but non-exclusive", "Keep drain unresolved"],
            "status": "superseded",
            "supersedes_record_id": "greg-tee-readiness-hold-001",
            "parent_record_ids": ["greg-tee-readiness-hold-001"],
            "rationale": verdict,
            "impact": 1 if verdict == READY_VERDICT else 0,
            "tags": ["greg", "tee-output", "postwrite", "drain-ack"],
            "metadata": {"profiles": profiles},
        },
    ]
    records[0]["child_record_ids"] = ["greg-tee-postwrite-drain-002"]
    write_json(out / "drp" / "decisions.json", records)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--inherited-readiness-run", required=True)
    args = parser.parse_args()

    root = Path(args.input_root)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pairs = find_results(root)
    results = [value for _path, value in pairs]
    profiles = build_profiles(results) if results else {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any, *, blocking: bool = True) -> None:
        checks.append({"name": name, "passed": bool(passed), "blocking": blocking, "detail": detail})

    systems = set(profiles)
    add("linux_and_macos_present", systems == {"Linux", "Darwin"}, sorted(systems))
    add(
        "platform_execution_complete",
        bool(results) and all(result["summary"]["execution_complete"] for result in results),
        [result.get("summary") for result in results],
    )
    for system, profile in profiles.items():
        add(
            f"{system}_startup_gates_pass",
            all(item["startup_gate_failures"] == 0 for item in profile.values()),
            {mode: item["startup_gate_failures"] for mode, item in profile.items()},
        )
        add(
            f"{system}_immediate_tail_loss_observed",
            profile["ack_immediate"]["failures"] > 0,
            profile["ack_immediate"],
            blocking=False,
        )
        add(
            f"{system}_output_complete_barrier_passes",
            profile["ack_output_complete"]["postwrite_barrier_failures"] == 0,
            profile["ack_output_complete"],
        )
        add(
            f"{system}_output_complete_results_clean",
            profile["ack_output_complete"]["failures"] == 0,
            profile["ack_output_complete"],
            blocking=False,
        )
        for mode in ("ack_postwrite_1ms", "ack_postwrite_5ms", "ack_postwrite_10ms", "ack_postwrite_25ms", "ack_quiescence_5ms", "direct_ack_safe_close"):
            add(
                f"{system}_{mode}_diagnostic",
                profile[mode]["failures"] == 0,
                profile[mode],
                blocking=False,
            )

    blocking = [item for item in checks if item["blocking"] and not item["passed"]]
    diagnostics = [item for item in checks if not item["blocking"]]
    output_complete_clean = bool(profiles) and all(
        platform["ack_output_complete"]["failures"] == 0
        and platform["ack_output_complete"]["postwrite_barrier_failures"] == 0
        for platform in profiles.values()
    )
    immediate_reproduced = bool(profiles) and any(
        platform["ack_immediate"]["failures"] > 0 for platform in profiles.values()
    )
    if blocking:
        verdict = "BLOCKED_POSTWRITE_EVIDENCE_INCOMPLETE"
    elif output_complete_clean and immediate_reproduced:
        verdict = READY_VERDICT
    else:
        verdict = "HOLD_POSTWRITE_DRAIN_BARRIER_NOT_SUFFICIENT"

    ttrace = build_ttrace(results, out)
    ttm = build_ttm(results, out)
    sdp = build_sdp(profiles, out)
    drp = build_drp(verdict, profiles, out)

    report = {
        "schema_version": "liminalqa-greg-postwrite-full-stack-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inherited_readiness_evidence": {
            "run": args.inherited_readiness_run,
            "verdict": "HOLD_READINESS_BARRIER_NOT_SUFFICIENT",
            "boundary": "Inherited exact-head evidence from the stacked base; no readiness-only claim is promoted here.",
        },
        "platform_results": [
            {"path": str(path), "sha256": sha256_file(path), "result": result}
            for path, result in pairs
        ],
        "profiles": profiles,
        "checks": checks,
        "blocking_checks": blocking,
        "diagnostic_observations": diagnostics,
        "layers": {
            "ttrace": ttrace,
            "ttm_db": ttm,
            "sdp": sdp,
            "drp": {"records": len(drp)},
        },
        "summary": {
            "verdict": verdict,
            "postwrite_drain_status": "SUPPORTED_NON_EXCLUSIVE" if verdict == READY_VERDICT else "UNRESOLVED",
            "sole_root_cause_status": "UNRESOLVED",
        },
        "notification_contract": {
            "permitted": verdict == READY_VERDICT,
            "comments_only": True,
            "state_changes": False,
            "may_claim_postwrite_drain_support": verdict == READY_VERDICT,
            "may_claim_drain_as_sole_cause": False,
            "must_disclose_output_complete_is_observational": True,
            "must_disclose_process_topology_changes": True,
        },
    }
    write_json(out / "greg-postwrite-full-stack-result.json", report)

    summary = [
        "# Greg tee-output post-write drain evidence",
        "",
        f"- verdict: **{verdict}**",
        f"- blocking checks: `{len(blocking)}`",
        f"- diagnostic observations: `{len(diagnostics)}`",
        f"- systems: `{', '.join(sorted(systems))}`",
        f"- T-Trace records: `{ttrace['records']}`",
        f"- TTM records: `{ttm['records']}`",
        f"- TTM replay errors: `{len(ttm['errors'])}`",
        f"- SDP selected: `{sdp['selected_hypothesis']}`",
        "",
        "The output-complete barrier is observational: it waits until every expected record is visible in the configured files.",
        "It is not an internal acknowledgement from the system tee implementation.",
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
