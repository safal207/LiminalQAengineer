#!/usr/bin/env python3
"""Validate space, transition, time, and causality before external notification."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--greg-result", required=True)
    parser.add_argument("--boris-result", required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-observation-age-minutes", type=int, default=60)
    args = parser.parse_args()

    greg_path = Path(args.greg_result)
    boris_path = Path(args.boris_result)
    review_path = Path(args.review_result)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    greg = json.loads(greg_path.read_text(encoding="utf-8"))
    boris = json.loads(boris_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc)
    greg_observed = parse_time(greg.get("observed_at"))
    boris_observed = parse_time(boris.get("observed_at"))
    max_age_seconds = args.max_observation_age_minutes * 60

    nodes = [
        {
            "id": "G_SOURCE",
            "space": "gdb/tee-output@c41f8ff383200320b746e953e92709ae1b505a71",
            "type": "exact_source",
            "time": "2023-08-18T01:40:37Z",
        },
        {
            "id": "G_ISSUE",
            "space": "gdb/tee-output#3",
            "type": "public_issue",
            "time": review["greg"]["selected_issue"].get("created_at"),
        },
        {
            "id": "G_BASELINE",
            "space": "isolated GitHub-hosted Linux child processes",
            "type": "deterministic_observation",
            "time": greg.get("observed_at"),
        },
        {
            "id": "G_COUNTERFACTUAL",
            "space": "same source and records; shutdown ordering replaced",
            "type": "causal_counterfactual",
            "time": greg.get("observed_at"),
        },
        {
            "id": "B_FORK_PRS",
            "space": "bcherny/openclaw#1,#2,#3",
            "type": "fork_pull_requests",
            "time": boris.get("observed_at"),
        },
        {
            "id": "B_UPSTREAM_PRS",
            "space": "openclaw/openclaw#58036,#58037,#58038",
            "type": "upstream_pull_requests",
            "time": "2026-04-04",
        },
        {
            "id": "B_FOLLOWUP",
            "space": "openclaw/openclaw@b474e098d15d8a0936153118adb6e28255b9071e",
            "type": "scope_correction",
            "time": "2026-04-05T07:32:51Z",
        },
        {
            "id": "B_CLAUDE_ISSUES",
            "space": "anthropics/claude-code#21151,#4937,#1554",
            "type": "assigned_public_issues",
            "time": boris.get("observed_at"),
        },
    ]

    greg_summary = greg.get("summary", {})
    boris_summary = boris.get("summary", {})
    static = greg.get("static_observation", {})

    space_checks = [
        check(
            "greg_exact_source_identity",
            greg.get("upstream", {}).get("repository") == "gdb/tee-output"
            and greg.get("upstream", {}).get("exact_sha")
            == "c41f8ff383200320b746e953e92709ae1b505a71",
            greg.get("upstream"),
        ),
        check(
            "greg_issue_identity",
            greg.get("upstream", {}).get("issue")
            == "https://github.com/gdb/tee-output/issues/3",
            greg.get("upstream", {}).get("issue"),
        ),
        check(
            "boris_three_fork_and_upstream_pairs",
            len(boris.get("pull_request_pairs", [])) == 3,
            [
                {
                    "fork": pair.get("fork", {}).get("html_url"),
                    "upstream": pair.get("upstream", {}).get("html_url"),
                }
                for pair in boris.get("pull_request_pairs", [])
            ],
        ),
        check(
            "boris_three_expected_claude_issues",
            sorted(
                issue.get("number")
                for issue in boris.get("assigned_claude_code_issues", [])
            )
            == [1554, 4937, 21151],
            [
                issue.get("html_url")
                for issue in boris.get("assigned_claude_code_issues", [])
            ],
        ),
    ]

    transition_checks = [
        check(
            "greg_static_shutdown_transition",
            static.get("close_calls_pause_before_drain") is True
            and static.get("drain_sends_sigint_before_wait") is True,
            static,
        ),
        check(
            "greg_baseline_completed",
            greg_summary.get("baseline_total_rounds", 0) >= 3,
            greg_summary,
        ),
        check(
            "greg_counterfactual_completed",
            greg_summary.get("patched_total_rounds", 0) >= 3,
            greg_summary,
        ),
        check(
            "boris_fork_open_to_upstream_merged_transition",
            boris_summary.get("fork_prs_verified_superseded") == 3
            and boris_summary.get("fork_prs_total") == 3,
            boris_summary,
        ),
        check(
            "boris_scope_correction_transition",
            boris_summary.get("followup_verified") is True,
            boris.get("upstream_followup", {}).get("checks"),
        ),
        check(
            "boris_current_issue_assignment_transition",
            boris_summary.get("assigned_issues_verified_current") == 3
            and boris_summary.get("assigned_issues_total") == 3,
            boris_summary,
        ),
    ]

    time_checks = [
        check(
            "greg_observation_fresh",
            greg_observed is not None
            and 0 <= (now - greg_observed).total_seconds() <= max_age_seconds,
            greg.get("observed_at"),
        ),
        check(
            "boris_observation_fresh",
            boris_observed is not None
            and 0 <= (now - boris_observed).total_seconds() <= max_age_seconds,
            boris.get("observed_at"),
        ),
        check(
            "upstream_merge_precedes_current_observation",
            all(
                parse_time(pair.get("upstream", {}).get("merged_at")) is not None
                and parse_time(pair.get("upstream", {}).get("merged_at"))
                < boris_observed
                for pair in boris.get("pull_request_pairs", [])
            )
            if boris_observed
            else False,
            [
                pair.get("upstream", {}).get("merged_at")
                for pair in boris.get("pull_request_pairs", [])
            ],
        ),
        check(
            "followup_after_three_merges",
            all(
                parse_time(pair.get("upstream", {}).get("merged_at"))
                < datetime(2026, 4, 5, 7, 32, 51, tzinfo=timezone.utc)
                for pair in boris.get("pull_request_pairs", [])
            ),
            "2026-04-05T07:32:51Z",
        ),
    ]

    greg_causal_confirmed = (
        greg_summary.get("baseline_failure_rounds", 0) > 0
        and greg_summary.get("patched_failure_rounds") == 0
        and greg_summary.get("patched_total_rounds", 0) >= 3
    )
    greg_nonrepro_ready = (
        greg_summary.get("baseline_failure_rounds") == 0
        and greg_summary.get("patched_failure_rounds") == 0
        and greg_summary.get("baseline_total_rounds", 0) >= 3
    )

    causality_checks = [
        check(
            "greg_claim_matches_counterfactual",
            greg_causal_confirmed or greg_nonrepro_ready,
            {
                "baseline_failures": greg_summary.get("baseline_failure_rounds"),
                "patched_failures": greg_summary.get("patched_failure_rounds"),
                "allowed_claim": (
                    "CONFIRMED_SHUTDOWN_DATA_LOSS_WITH_PASSING_COUNTERFACTUAL"
                    if greg_causal_confirmed
                    else "NOT_REPRODUCED_ON_THIS_RUN_STATIC_RISK_REMAINS"
                    if greg_nonrepro_ready
                    else "BLOCKED"
                ),
            },
        ),
        check(
            "boris_superseded_claim_is_lifecycle_not_code_approval",
            all(
                pair.get("verdict") == "CLOSE_AS_SUPERSEDED"
                and pair.get("upstream", {}).get("merged") is True
                for pair in boris.get("pull_request_pairs", [])
            ),
            [pair.get("verdict") for pair in boris.get("pull_request_pairs", [])],
        ),
        check(
            "boris_issue_recommendations_not_presented_as_implementation_facts",
            set(boris.get("review_contracts", {}).values())
            == {
                "KEEP_OPEN_AND_DEFINE_VISIBLE_PRIMARY_IDENTIFIER_CONTRACT",
                "VERIFY_CURRENT_CLI_PARITY_THEN_CLOSE_OR_NARROW",
                "CURRENT_VERSION_REPRO_REQUIRED",
            },
            boris.get("review_contracts"),
        ),
        check(
            "authority_boundary",
            boris.get("authority", {}).get("approval") is False
            and boris.get("authority", {}).get("close") is False
            and boris.get("authority", {}).get("merge") is False
            and greg.get("authority", {}).get("approval") is False
            and greg.get("authority", {}).get("merge") is False,
            {"greg": greg.get("authority"), "boris": boris.get("authority")},
        ),
    ]

    all_checks = space_checks + transition_checks + time_checks + causality_checks
    blocking = [item for item in all_checks if not item["passed"]]

    if blocking:
        overall = "BLOCKED_DO_NOT_NOTIFY"
    elif greg_causal_confirmed:
        overall = "READY_TO_NOTIFY_CONFIRMED_GREG_AND_VERIFIED_BORIS"
    elif greg_nonrepro_ready:
        overall = "READY_TO_NOTIFY_BORIS_GREG_NONREPRO_ONLY"
    else:
        overall = "BLOCKED_DO_NOT_NOTIFY"

    edges = [
        {
            "from": "G_SOURCE",
            "to": "G_BASELINE",
            "relation": "executed_exact_source",
            "status": "PASS" if space_checks[0]["passed"] else "FAIL",
        },
        {
            "from": "G_BASELINE",
            "to": "G_COUNTERFACTUAL",
            "relation": "same_inputs_shutdown_order_only_changed",
            "status": "CAUSAL_SUPPORT"
            if greg_causal_confirmed
            else "NONREPRO_SUPPORT"
            if greg_nonrepro_ready
            else "BLOCKED",
        },
        {
            "from": "B_FORK_PRS",
            "to": "B_UPSTREAM_PRS",
            "relation": "same_author_and_title_upstream_merged",
            "status": "PASS"
            if transition_checks[3]["passed"]
            else "FAIL",
        },
        {
            "from": "B_UPSTREAM_PRS",
            "to": "B_FOLLOWUP",
            "relation": "later_scope_correction",
            "status": "PASS"
            if transition_checks[4]["passed"] and time_checks[3]["passed"]
            else "FAIL",
        },
        {
            "from": "B_CLAUDE_ISSUES",
            "to": "B_CLAUDE_ISSUES",
            "relation": "current_state_requires_future_validation_before_close",
            "status": "PASS" if causality_checks[2]["passed"] else "FAIL",
        },
    ]

    message_contract = {
        "greg": {
            "notify": overall
            in {
                "READY_TO_NOTIFY_CONFIRMED_GREG_AND_VERIFIED_BORIS",
                "READY_TO_NOTIFY_BORIS_GREG_NONREPRO_ONLY",
            },
            "allowed_classification": (
                "CONFIRMED_SHUTDOWN_DATA_LOSS_WITH_PASSING_COUNTERFACTUAL"
                if greg_causal_confirmed
                else "NOT_REPRODUCED_ON_THIS_RUN_STATIC_RISK_REMAINS"
                if greg_nonrepro_ready
                else "NONE"
            ),
            "forbidden_claims": [
                "all environments are affected",
                "production data has been lost",
                "the proposed counterfactual is a complete production patch",
            ],
        },
        "boris_openclaw": {
            "notify": overall != "BLOCKED_DO_NOT_NOTIFY",
            "allowed_classification": "CLOSE_AS_SUPERSEDED",
            "forbidden_claims": [
                "the fork PRs still need code approval",
                "the fixes preserve the entire prompt prefix",
                "sorting removes order-dependent name collisions",
            ],
        },
        "boris_claude_issues": {
            "notify": overall != "BLOCKED_DO_NOT_NOTIFY",
            "allowed_classification": "REVIEW_RECOMMENDATIONS_ONLY",
            "forbidden_claims": [
                "issue #4937 is already implemented without current CLI verification",
                "issue #1554 is fixed without current-version reproduction",
                "issue #21151 has a confirmed implementation defect beyond its public report",
            ],
        },
    }

    result = {
        "schema_version": "liminalqa-space-transition-time-causal-gate-v1",
        "validated_at": now.isoformat().replace("+00:00", "Z"),
        "overall_verdict": overall,
        "coordinate_model": {
            "space": "repository, exact SHA, issue or PR identity, runtime context",
            "transition": "before state -> action/state change -> after state",
            "time": "source, merge, correction, and fresh observation timestamps",
            "causality": "claim promoted only when exact observation and bounded counterfactual support it",
        },
        "nodes": nodes,
        "edges": edges,
        "checks": {
            "space": space_checks,
            "transition": transition_checks,
            "time": time_checks,
            "causality": causality_checks,
        },
        "blocking_checks": blocking,
        "message_contract": message_contract,
        "input_hashes": {
            str(greg_path): sha256_file(greg_path),
            str(boris_path): sha256_file(boris_path),
            str(review_path): sha256_file(review_path),
        },
        "authority": {
            "external_notification_authorized_by_gate": overall
            != "BLOCKED_DO_NOT_NOTIFY",
            "external_state_change": False,
            "approval": False,
            "close": False,
            "merge": False,
        },
    }

    result_path = output_dir / "causal-gate-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    mermaid = "\n".join(
        [
            "# Space–Transition–Time causal gate",
            "",
            f"Overall verdict: **{overall}**",
            "",
            "```mermaid",
            "flowchart LR",
            '  GS["Greg exact source SHA"] -->|execute| GB["Baseline immediate close"]',
            '  GB -->|shutdown order only changed| GC["Safe-drain counterfactual"]',
            '  BF["Boris fork PRs open"] -->|same title/author| BU["Upstream PRs merged"]',
            '  BU -->|later correction| BC["Narrowed prompt-cache claims"]',
            '  BI["Claude issues open + assigned"] -->|future verification required| BI',
            "```",
            "",
            "## Message classification",
            "",
            f"- Greg: `{message_contract['greg']['allowed_classification']}`",
            f"- Boris fork PRs: `{message_contract['boris_openclaw']['allowed_classification']}`",
            f"- Boris Claude issues: `{message_contract['boris_claude_issues']['allowed_classification']}`",
            "",
            f"Blocking checks: `{len(blocking)}`",
            "",
        ]
    )
    (output_dir / "causal-gate-summary.md").write_text(mermaid, encoding="utf-8")

    checksums = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksums.append(f"{sha256_file(path)}  {path.name}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    print(mermaid)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
