#!/usr/bin/env python3
"""Fail-closed validation for the Greg tee-output full-stack packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-age-minutes", type=int, default=90)
    args = parser.parse_args()

    result_path = Path(args.result)
    result = load(result_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    config = result.get("config", {})
    components = config.get("components", {})
    expected_pins = {
        "garden_liminal": "6c30422d0492ec312a35624322f90a7761419655",
        "ltp": "6284d2fee3f729ceacd688e74c5d67beea1ff3c7",
        "liminaldb": "75ef9f7f403a34c60aa2ceba4cb3c97870d73e77",
        "liminalosai": "a2c5783287a9def4b4254b9436c2e75468613dca",
    }
    check("subject_exact_sha", config.get("subject", {}).get("exact_sha") == "c41f8ff383200320b746e953e92709ae1b505a71")
    for name, sha in expected_pins.items():
        check(f"component_pin_{name}", components.get(name, {}).get("exact_sha") == sha)

    platform_results = result.get("platform_results", [])
    systems = {entry.get("result", {}).get("platform", {}).get("system") for entry in platform_results}
    check("linux_and_macos_present", systems == {"Linux", "Darwin"}, sorted(value for value in systems if value))
    check("two_platform_results", len(platform_results) == 2, len(platform_results))
    check("no_platform_timeouts", result.get("summary", {}).get("timeouts") == 0)

    layers = result.get("layers", {})
    check("garden_contract_passed", layers.get("garden", {}).get("passed") is True)
    check("garden_no_runtime_overclaim", layers.get("garden", {}).get("runtime_claim") is False)
    check("ltp_replay_passed", layers.get("ltp", {}).get("passed") is True)
    check("liminaldb_replay_passed", layers.get("liminaldb", {}).get("passed") is True)
    check(
        "liminalosai_advisory_only",
        layers.get("liminalosai", {}).get("authority", {}).get("can_confirm_bug") is False
        and layers.get("liminalosai", {}).get("authority", {}).get("can_authorize_notification") is False,
    )
    check("component_contracts_passed", result.get("component_contracts", {}).get("passed") is True)

    observed_at = parse_time(result["observed_at"])
    age_minutes = (datetime.now(timezone.utc) - observed_at).total_seconds() / 60.0
    check("fresh_observation", 0 <= age_minutes <= args.max_age_minutes, round(age_minutes, 3))

    notification = result.get("notification_contract", {})
    check("comments_only", notification.get("comments_only") is True)
    check("no_state_changes", notification.get("state_changes") is False)
    check("no_approval", notification.get("approval") is False)
    check("no_close", notification.get("close") is False)
    check("no_merge", notification.get("merge") is False)

    source_blocking = result.get("summary", {}).get("blocking_checks", [])
    check("builder_has_no_blocking_checks", not source_blocking, source_blocking)
    verdict = result.get("summary", {}).get("verdict", "")
    check("verdict_notification_safe", verdict.startswith("READY_TO_NOTIFY"), verdict)
    check("permission_matches_verdict", notification.get("permitted") is True)

    failed = [item for item in checks if not item["passed"]]
    overall = "GREG_FULL_STACK_READY_TO_NOTIFY" if not failed else "BLOCKED_DO_NOT_NOTIFY"
    gate = {
        "schema_version": "liminalqa-greg-tee-full-stack-gate-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input": {"path": str(result_path), "sha256": sha256_file(result_path)},
        "checks": checks,
        "blocking_checks": failed,
        "overall_verdict": overall,
        "message_contract": {
            "permitted": not failed,
            "must_quote_stack_verdict": verdict,
            "must_distinguish_non_reproduction_from_disproof": True,
            "must_name_platform_coordinates": True,
            "must_disclose_contract_adapters": True,
            "comments_only": True,
            "state_changes": False,
        },
    }
    (output_dir / "gate-result.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    summary = "\n".join([
        "# Greg tee-output full-stack gate",
        "",
        f"- checks: `{len(checks) - len(failed)}/{len(checks)}`",
        f"- blocking checks: `{len(failed)}`",
        f"- stack verdict: `{verdict}`",
        f"- gate verdict: **{overall}**",
        "",
    ])
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
