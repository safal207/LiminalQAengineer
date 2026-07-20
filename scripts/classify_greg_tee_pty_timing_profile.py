#!/usr/bin/env python3
"""Promote a reproducible symptom without promoting an unproven root cause.

The broad stack builder intentionally returns HOLD when baseline and shutdown
counterfactual both fail. This classifier may permit a narrower notification
only when the raw matrix proves a stable cross-platform PTY timing profile:

* non-PTY baseline coordinates all pass;
* PTY 0 ms baseline fails for both issue-shaped and direct-fd paths;
* PTY 100 ms baseline passes for both paths;
* the profile reproduces on Linux and macOS;
* the shutdown counterfactual remains non-clean.

The resulting message may report the symptom. It may not claim that SIGINT,
startup readiness, PTY setup, parent-lifetime, or another candidate is the
confirmed sole cause.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


VERDICT = "READY_TO_NOTIFY_PTY_TIMING_DATA_LOSS_CAUSE_UNRESOLVED"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def failures(result: dict[str, Any], scenario: str, pty: int, delay: int, mode: str) -> tuple[int, int]:
    key = f"{scenario}|pty={pty}|delay={delay}|{mode}"
    bucket = result["coordinates"][key]
    return int(bucket["failures"]), int(bucket["total"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    result_path = Path(args.result)
    stack = load(result_path)
    checks: list[dict[str, Any]] = []
    platform_profiles: dict[str, Any] = {}

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    platform_entries = stack.get("platform_results", [])
    systems = {entry.get("result", {}).get("platform", {}).get("system") for entry in platform_entries}
    add("linux_and_macos_present", systems == {"Linux", "Darwin"}, sorted(value for value in systems if value))
    add("initial_builder_hold", stack.get("summary", {}).get("verdict") == "HOLD_COUNTERFACTUAL_INCONCLUSIVE", stack.get("summary", {}).get("verdict"))

    for entry in platform_entries:
        platform_result = entry["result"]
        system = platform_result["platform"]["system"]
        nonpty_baseline = []
        pty_zero_baseline = []
        pty_hundred_baseline = []
        pty_short_patched = []
        for scenario in ("issue", "fd"):
            for delay in (0, 1, 10, 100):
                nonpty_baseline.append((*failures(platform_result, scenario, 0, delay, "baseline"), scenario, delay))
            pty_zero_baseline.append((*failures(platform_result, scenario, 1, 0, "baseline"), scenario))
            pty_hundred_baseline.append((*failures(platform_result, scenario, 1, 100, "baseline"), scenario))
            for delay in (0, 1, 10):
                pty_short_patched.append((*failures(platform_result, scenario, 1, delay, "patched"), scenario, delay))

        nonpty_failures = sum(item[0] for item in nonpty_baseline)
        pty_zero_failures = sum(item[0] for item in pty_zero_baseline)
        pty_zero_total = sum(item[1] for item in pty_zero_baseline)
        pty_hundred_failures = sum(item[0] for item in pty_hundred_baseline)
        patched_short_failures = sum(item[0] for item in pty_short_patched)
        profile = {
            "nonpty_baseline_failures": nonpty_failures,
            "pty_zero_baseline_failures": pty_zero_failures,
            "pty_zero_baseline_total": pty_zero_total,
            "pty_hundred_baseline_failures": pty_hundred_failures,
            "pty_short_patched_failures": patched_short_failures,
            "platform_verdict": platform_result["summary"]["verdict"],
        }
        platform_profiles[system] = profile
        add(f"{system}_nonpty_all_pass", nonpty_failures == 0, nonpty_baseline)
        add(f"{system}_pty_zero_both_paths_fail", pty_zero_failures == pty_zero_total and pty_zero_total > 0, pty_zero_baseline)
        add(f"{system}_pty_hundred_both_paths_pass", pty_hundred_failures == 0, pty_hundred_baseline)
        add(f"{system}_shutdown_counterfactual_not_clean", patched_short_failures > 0, pty_short_patched)

    blocking = [item for item in checks if not item["passed"]]
    promoted = not blocking
    if promoted:
        stack["summary"]["previous_verdict"] = stack["summary"]["verdict"]
        stack["summary"]["verdict"] = VERDICT
        stack["summary"]["symptom_status"] = "CONFIRMED_IN_BOUNDED_MATRIX"
        stack["summary"]["root_cause_status"] = "UNRESOLVED"
        stack["summary"]["profile"] = platform_profiles
        stack["notification_contract"].update(
            {
                "permitted": True,
                "symptom_claim_permitted": True,
                "root_cause_claim_permitted": False,
                "sigint_cause_claim_permitted": False,
                "startup_readiness_claim_permitted": False,
                "startup_readiness_candidate_permitted": True,
                "must_name_pty_and_delay_coordinates": True,
                "must_disclose_shutdown_counterfactual_inconclusive": True,
            }
        )
        result_path.write_text(json.dumps(stack, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {
        "schema_version": "liminalqa-greg-tee-pty-timing-classification-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": checks,
        "blocking_checks": blocking,
        "platform_profiles": platform_profiles,
        "promoted": promoted,
        "verdict": VERDICT if promoted else "HOLD_PROFILE_NOT_PROVEN",
        "claim_boundary": {
            "symptom": "permitted" if promoted else "not_permitted",
            "sole_root_cause": "prohibited",
            "sigint_as_confirmed_cause": "prohibited",
            "startup_readiness_as_confirmed_cause": "prohibited",
            "startup_readiness_as_next_counterfactual": "permitted",
        },
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"promoted": promoted, "verdict": report["verdict"], "blocking": len(blocking)}))
    return 0 if promoted else 1


if __name__ == "__main__":
    raise SystemExit(main())
