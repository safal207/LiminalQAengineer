#!/usr/bin/env python3
"""Build an honest multi-repository evidence packet from platform results.

GardenLiminal is represented by a lifecycle contract adapter because hosted
GitHub runners cannot provide a trustworthy privileged/rootless namespace
claim. LTP receives a deterministic replay trace. LiminalDB receives an
append-only hash chain. LiminalOSAI produces advisory-only observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_platform_results(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, load_json(path)) for path in sorted(root.rglob("greg-platform-result.json"))]


def find_platform_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sorted(root.rglob("greg-platform-events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def coordinate_key(event: dict[str, Any]) -> str:
    coordinate = event["coordinate"]
    platform_name = event["platform"]["system"]
    return "|".join(
        [
            platform_name,
            coordinate["scenario"],
            f"pty={int(coordinate['pty'])}",
            f"delay={coordinate['delay_ms']}",
            coordinate["shutdown"],
            f"round={coordinate['round']}",
        ]
    )


def build_garden(events: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    garden_dir = output_dir / "garden"
    garden_dir.mkdir(parents=True, exist_ok=True)
    seed = """apiVersion: v0
kind: Seed
meta:
  name: greg-tee-output-evidence
  id: greg-tee-output-issue-3
rootfs:
  path: exact-github-runner-environment
entrypoint:
  cmd: [\"python\", \"-u\", \"scripts/greg_tee_cross_platform_evidence.py\"]
limits:
  cpu:
    shares: 256
  memory:
    max: \"512Mi\"
  pids:
    max: 128
security:
  hostname: greg-tee-evidence
  drop_caps: [\"NET_ADMIN\", \"SYS_ADMIN\"]
  seccomp_profile: \"documented-not-enforced-on-hosted-runner\"
store:
  kind: \"liminaldb-contract-adapter\"
"""
    (garden_dir / "seed.yaml").write_text(seed, encoding="utf-8")

    lifecycle: list[dict[str, Any]] = []
    mapping = {
        "RUN_CREATED": "RUN_CREATED",
        "OBSERVER_BOUND": "SEED_LOADED",
        "TEE_CREATED": "PROCESS_START",
        "REDIRECT_ACTIVE": "REDIRECT_ACTIVE",
        "ISSUE_MARKERS_WRITTEN": "PROCESS_WRITE",
        "TRACEBACK_WRITTEN": "PROCESS_WRITE",
        "FD_RECORDS_WRITTEN": "PROCESS_WRITE",
        "CLOSE_REQUESTED": "PROCESS_CLOSE_REQUESTED",
        "CLOSE_COMPLETED": "PROCESS_CLOSE_COMPLETED",
        "FILES_OBSERVED": "EVIDENCE_OBSERVED",
        "VERIFICATION_COMPLETED": "PROCESS_EXIT",
    }
    for item in sorted(events, key=lambda value: (value["wall_time_ns"], value["monotonic_ns"])):
        lifecycle.append(
            {
                "ts_ns": item["wall_time_ns"],
                "run": coordinate_key(item),
                "event": mapping.get(item["name"], item["name"]),
                "source_event": item["name"],
                "details": item.get("details", {}),
            }
        )
    with (garden_dir / "lifecycle.jsonl").open("w", encoding="utf-8") as handle:
        for item in lifecycle:
            handle.write(json.dumps(item, sort_keys=True) + "\n")

    runs: dict[str, list[str]] = {}
    for item in lifecycle:
        runs.setdefault(item["run"], []).append(item["event"])
    required = ["RUN_CREATED", "SEED_LOADED", "PROCESS_START", "PROCESS_CLOSE_REQUESTED", "PROCESS_CLOSE_COMPLETED", "EVIDENCE_OBSERVED", "PROCESS_EXIT"]
    invalid = {
        run: [name for name in required if name not in names]
        for run, names in runs.items()
        if any(name not in names for name in required)
    }
    report = {
        "schema_version": "liminalqa-garden-contract-report-v1",
        "integration_mode": "CONTRACT_ADAPTER_NO_PRIVILEGED_RUNTIME",
        "runtime_claim": False,
        "runs": len(runs),
        "events": len(lifecycle),
        "invalid_runs": invalid,
        "passed": not invalid and bool(runs),
        "boundary": "No claim that hosted runners executed Garden namespaces, cgroups or seccomp.",
    }
    write_json(garden_dir / "garden-contract-report.json", report)
    return report


def build_ltp(events: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    ltp_dir = output_dir / "ltp"
    ltp_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in events:
        grouped.setdefault(coordinate_key(item), []).append(item)

    traces: list[dict[str, Any]] = []
    decisions: dict[str, str] = {}
    violations: list[dict[str, Any]] = []
    for run, items in sorted(grouped.items()):
        items.sort(key=lambda value: value["sequence"])
        previous_id: str | None = None
        expected_sequence = 1
        final_pass: bool | None = None
        for item in items:
            event_id = hashlib.sha256(f"{run}|{item['sequence']}|{item['name']}".encode()).hexdigest()[:24]
            if item["sequence"] != expected_sequence:
                violations.append({"run": run, "type": "NON_MONOTONIC_SEQUENCE", "expected": expected_sequence, "observed": item["sequence"]})
            phase = "pre" if item["name"] in {"RUN_CREATED", "OBSERVER_BOUND", "TEE_CREATED"} else "post" if item["name"] in {"FILES_OBSERVED", "VERIFICATION_COMPLETED"} else "action"
            record = {
                "trace_id": run,
                "event_id": event_id,
                "parent_event_id": previous_id,
                "sequence": item["sequence"],
                "timestamp_ns": item["wall_time_ns"],
                "phase": phase,
                "event": item["name"],
                "coordinate": item["coordinate"],
                "evidence": item.get("details", {}),
            }
            traces.append(record)
            previous_id = event_id
            expected_sequence += 1
            if item["name"] == "VERIFICATION_COMPLETED":
                final_pass = bool(item.get("details", {}).get("passed"))
        if not items or items[-1]["name"] != "VERIFICATION_COMPLETED":
            decisions[run] = "drift"
            violations.append({"run": run, "type": "MISSING_TERMINAL_VERIFICATION"})
        elif final_pass:
            decisions[run] = "admissible"
        else:
            decisions[run] = "rejected"

    with (ltp_dir / "trace.jsonl").open("w", encoding="utf-8") as handle:
        for item in traces:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    counts = {name: list(decisions.values()).count(name) for name in ("admissible", "drift", "rejected")}
    report = {
        "schema_version": "liminalqa-ltp-replay-report-v1",
        "integration_mode": "CONTRACT_ADAPTER_WITH_DETERMINISTIC_REPLAY",
        "traces": len(decisions),
        "events": len(traces),
        "decisions": counts,
        "violations": violations,
        "passed": not violations,
        "boundary": "Adapter validates this evidence path; it is not a claim of hosted LTP service execution.",
    }
    write_json(ltp_dir / "replay-report.json", report)
    return report


def build_liminaldb(events: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    db_dir = output_dir / "liminaldb"
    db_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    previous_hash = "0" * 64
    for sequence, item in enumerate(sorted(events, key=lambda value: (value["wall_time_ns"], coordinate_key(value), value["sequence"])), 1):
        payload = {
            "pattern": "greg/tee-output/lifecycle",
            "strength": 1.0,
            "coordinate": item["coordinate"],
            "platform": item["platform"],
            "event": item["name"],
            "details": item.get("details", {}),
            "timestamp_ns": item["wall_time_ns"],
        }
        record_hash = hashlib.sha256(previous_hash.encode() + canonical(payload)).hexdigest()
        record = {"sequence": sequence, "previous_hash": previous_hash, "record_hash": record_hash, "payload": payload}
        records.append(record)
        previous_hash = record_hash
    with (db_dir / "impulses.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    replay_previous = "0" * 64
    replay_errors = []
    for expected_sequence, record in enumerate(records, 1):
        expected_hash = hashlib.sha256(replay_previous.encode() + canonical(record["payload"])).hexdigest()
        if record["sequence"] != expected_sequence:
            replay_errors.append({"sequence": expected_sequence, "type": "SEQUENCE_MISMATCH"})
        if record["previous_hash"] != replay_previous:
            replay_errors.append({"sequence": expected_sequence, "type": "PREVIOUS_HASH_MISMATCH"})
        if record["record_hash"] != expected_hash:
            replay_errors.append({"sequence": expected_sequence, "type": "RECORD_HASH_MISMATCH"})
        replay_previous = record["record_hash"]
    report = {
        "schema_version": "liminalqa-liminaldb-replay-report-v1",
        "integration_mode": "FILE_BACKED_EVENT_SOURCED_ADAPTER_NO_LIVE_DAEMON",
        "records": len(records),
        "head_hash": previous_hash,
        "replay_errors": replay_errors,
        "passed": bool(records) and not replay_errors,
        "boundary": "Append-only adapter only; no claim that a live LiminalDB daemon persisted these records.",
    }
    write_json(db_dir / "replay-report.json", report)
    return report


def build_liminalosai(platform_results: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    osai_dir = output_dir / "liminalosai"
    osai_dir.mkdir(parents=True, exist_ok=True)
    by_platform = {
        item["platform"]["system"]: {
            "baseline_failures": item["summary"]["baseline_failures"],
            "patched_failures": item["summary"]["patched_failures"],
            "timeouts": item["summary"]["timeouts"],
            "verdict": item["summary"]["verdict"],
        }
        for item in platform_results
    }
    baseline_values = {value["baseline_failures"] for value in by_platform.values()}
    observations = []
    if len(baseline_values) > 1:
        observations.append("ENVIRONMENT_DIVERGENCE_OBSERVED")
    else:
        observations.append("NO_CROSS_PLATFORM_DIVERGENCE_IN_FAILURE_COUNT")
    if all(value["baseline_failures"] == 0 for value in by_platform.values()):
        observations.append("BOUNDED_NON_REPRODUCTION")
    if any(value["patched_failures"] for value in by_platform.values()):
        observations.append("COUNTERFACTUAL_NOT_CLEAN")
    observations.append("STATIC_SHUTDOWN_ORDER_RISK_REMAINS")
    advisory = {
        "schema_version": "liminalqa-liminalosai-advisory-v1",
        "integration_mode": "ADVISORY_ONLY_RULE_BASED_OBSERVER",
        "platforms": by_platform,
        "observations": observations,
        "authority": {"can_confirm_bug": False, "can_authorize_notification": False, "can_change_external_state": False},
        "boundary": "Rule-based advisory derived from formal evidence; not LiminalOSAI safety enforcement or cognition.",
    }
    write_json(osai_dir / "advisory.json", advisory)
    return advisory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--contracts", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_root = Path(args.input_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(Path(args.config))
    contracts = load_json(Path(args.contracts))
    result_pairs = find_platform_results(input_root)
    platform_results = [value for _path, value in result_pairs]
    events = find_platform_events(input_root)

    garden = build_garden(events, output_dir)
    ltp = build_ltp(events, output_dir)
    liminaldb = build_liminaldb(events, output_dir)
    liminalosai = build_liminalosai(platform_results, output_dir)

    baseline_failures = sum(item["summary"]["baseline_failures"] for item in platform_results)
    patched_failures = sum(item["summary"]["patched_failures"] for item in platform_results)
    timeouts = sum(item["summary"]["timeouts"] for item in platform_results)
    blocking = []
    if len({item["platform"]["system"] for item in platform_results}) != 2:
        blocking.append("MISSING_LINUX_OR_MACOS_RESULT")
    if timeouts:
        blocking.append("PLATFORM_TIMEOUTS")
    if not garden["passed"]:
        blocking.append("GARDEN_CONTRACT_FAILED")
    if not ltp["passed"]:
        blocking.append("LTP_REPLAY_FAILED")
    if not liminaldb["passed"]:
        blocking.append("LIMINALDB_REPLAY_FAILED")
    if not contracts.get("passed"):
        blocking.append("COMPONENT_CONTRACT_VALIDATION_FAILED")

    if blocking:
        verdict = "BLOCKED_DO_NOT_NOTIFY"
    elif baseline_failures and not patched_failures:
        verdict = "READY_TO_NOTIFY_DATA_LOSS_WITH_COUNTERFACTUAL_SUPPORT"
    elif baseline_failures:
        verdict = "HOLD_COUNTERFACTUAL_INCONCLUSIVE"
    else:
        verdict = "READY_TO_NOTIFY_CROSS_PLATFORM_NON_REPRODUCTION_STATIC_RISK_REMAINS"

    stack = {
        "schema_version": "liminalqa-greg-tee-full-stack-result-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": config,
        "component_contracts": contracts,
        "platform_results": [
            {"path": str(path), "sha256": sha256_file(path), "result": value}
            for path, value in result_pairs
        ],
        "layers": {"garden": garden, "ltp": ltp, "liminaldb": liminaldb, "liminalosai": liminalosai},
        "summary": {
            "baseline_failures": baseline_failures,
            "patched_failures": patched_failures,
            "timeouts": timeouts,
            "blocking_checks": blocking,
            "verdict": verdict,
        },
        "notification_contract": {
            "permitted": verdict.startswith("READY_TO_NOTIFY"),
            "comments_only": True,
            "state_changes": False,
            "approval": False,
            "close": False,
            "merge": False,
        },
    }
    write_json(output_dir / "greg-tee-full-stack-result.json", stack)
    summary = "\n".join([
        "# Greg tee-output full-stack evidence",
        "",
        f"- platform results: `{len(platform_results)}`",
        f"- baseline failures: `{baseline_failures}`",
        f"- patched failures: `{patched_failures}`",
        f"- timeouts: `{timeouts}`",
        f"- blocking checks: `{len(blocking)}`",
        f"- verdict: **{verdict}**",
        "",
        "Garden and LiminalDB are explicit contract adapters; LTP replay is deterministic; LiminalOSAI is advisory-only.",
        "",
    ])
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    checksum_lines = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksum_lines.append(f"{sha256_file(path)}  {path.relative_to(output_dir)}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
