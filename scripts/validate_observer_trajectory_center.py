#!/usr/bin/env python3
"""Validate observer origin, coordinate orientation, and trajectory continuity.

This is a second fail-closed layer after the causal graph. It prevents a
correct local observation from being projected into the wrong repository,
state, time, or authority frame.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
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
    parser.add_argument("--causal-result", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    greg_path = Path(args.greg_result)
    boris_path = Path(args.boris_result)
    causal_path = Path(args.causal_result)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    greg = json.loads(greg_path.read_text(encoding="utf-8"))
    boris = json.loads(boris_path.read_text(encoding="utf-8"))
    causal = json.loads(causal_path.read_text(encoding="utf-8"))

    observer = {
        "id": "N_READ_ONLY_EVIDENCE_OBSERVER",
        "position": "outside all third-party repositories and product runtimes",
        "capabilities": [
            "read public source and metadata",
            "execute exact public source in isolated local CI",
            "construct bounded counterfactuals",
            "publish evidence comments after gates pass",
        ],
        "prohibited_role_transitions": [
            "observer -> owner",
            "observer -> approver",
            "observer -> maintainer",
            "observer -> closer",
            "observer -> merger",
            "observer -> production operator",
        ],
    }

    greg_origin = {
        "id": "O_GREG",
        "X_space": "gdb/tee-output@c41f8ff383200320b746e953e92709ae1b505a71 + issue #3",
        "Y_state": "exact upstream shutdown implementation before external modification",
        "Z_context": "isolated GitHub-hosted Linux child process; direct fd writes; no remote runtime",
        "T_time": greg.get("observed_at"),
        "orientation": "source -> baseline immediate close -> bounded shutdown-order counterfactual",
    }

    boris_origin = {
        "id": "O_BORIS",
        "X_space": "bcherny/openclaw fork PRs + openclaw/openclaw upstream PRs + anthropics/claude-code issues",
        "Y_state": "current public lifecycle state observed through read-only GitHub API",
        "Z_context": "public metadata only; no code execution or issue mutation",
        "T_time": boris.get("observed_at"),
        "orientation": "fork-open -> upstream-merged -> later scope correction; issue-open -> future validation required",
    }

    greg_summary = greg.get("summary", {})
    boris_summary = boris.get("summary", {})
    causal_contract = causal.get("message_contract", {})

    trajectories = [
        {
            "id": "TAU_GREG_BASELINE",
            "origin": "O_GREG",
            "observer": observer["id"],
            "nodes": [
                "exact_source_sha",
                "installed_exact_package",
                "unique_fd_records",
                "immediate_close",
                "persisted_file_verification",
            ],
            "changed_variables": [],
            "endpoint_classification": greg_summary.get("verdict"),
        },
        {
            "id": "TAU_GREG_COUNTERFACTUAL",
            "origin": "O_GREG",
            "observer": observer["id"],
            "nodes": [
                "same_exact_source_sha",
                "same_unique_fd_records",
                "shutdown_order_only_changed",
                "natural_eof_drain",
                "persisted_file_verification",
            ],
            "changed_variables": ["shutdown_order"],
            "endpoint_classification": causal_contract.get("greg", {}).get(
                "allowed_classification"
            ),
        },
        {
            "id": "TAU_BORIS_OPENCLAW",
            "origin": "O_BORIS",
            "observer": observer["id"],
            "nodes": [
                "fork_pr_open",
                "identity_edge_same_author_and_title",
                "upstream_pr_merged_at_exact_sha",
                "later_scope_correction",
                "superseded_recommendation",
            ],
            "changed_variables": ["repository_frame", "lifecycle_time"],
            "endpoint_classification": causal_contract.get("boris_openclaw", {}).get(
                "allowed_classification"
            ),
        },
        {
            "id": "TAU_BORIS_CLAUDE_ISSUES",
            "origin": "O_BORIS",
            "observer": observer["id"],
            "nodes": [
                "issue_identity",
                "current_open_state",
                "current_assignment",
                "bounded_review_contract",
                "future_validation_before_resolution",
            ],
            "changed_variables": [],
            "endpoint_classification": causal_contract.get(
                "boris_claude_issues", {}
            ).get("allowed_classification"),
        },
    ]

    expected_greg_sha = "c41f8ff383200320b746e953e92709ae1b505a71"
    expected_followup_sha = "b474e098d15d8a0936153118adb6e28255b9071e"

    origin_checks = [
        check(
            "greg_origin_exact",
            greg.get("upstream", {}).get("repository") == "gdb/tee-output"
            and greg.get("upstream", {}).get("exact_sha") == expected_greg_sha
            and greg.get("upstream", {}).get("issue")
            == "https://github.com/gdb/tee-output/issues/3",
            greg_origin,
        ),
        check(
            "boris_origin_exact",
            len(boris.get("pull_request_pairs", [])) == 3
            and sorted(
                issue.get("number")
                for issue in boris.get("assigned_claude_code_issues", [])
            )
            == [1554, 4937, 21151]
            and boris.get("upstream_followup", {}).get("sha")
            == expected_followup_sha,
            boris_origin,
        ),
        check(
            "origins_have_observation_time",
            parse_time(greg_origin["T_time"]) is not None
            and parse_time(boris_origin["T_time"]) is not None,
            {"greg": greg_origin["T_time"], "boris": boris_origin["T_time"]},
        ),
    ]

    orientation_checks = [
        check(
            "greg_trajectory_keeps_one_origin",
            all(
                trajectory["origin"] == "O_GREG"
                for trajectory in trajectories
                if trajectory["id"].startswith("TAU_GREG")
            ),
            [
                {"id": item["id"], "origin": item["origin"]}
                for item in trajectories
                if item["id"].startswith("TAU_GREG")
            ],
        ),
        check(
            "boris_trajectory_keeps_one_origin",
            all(
                trajectory["origin"] == "O_BORIS"
                for trajectory in trajectories
                if trajectory["id"].startswith("TAU_BORIS")
            ),
            [
                {"id": item["id"], "origin": item["origin"]}
                for item in trajectories
                if item["id"].startswith("TAU_BORIS")
            ],
        ),
        check(
            "counterfactual_changes_one_variable",
            next(
                item
                for item in trajectories
                if item["id"] == "TAU_GREG_COUNTERFACTUAL"
            )["changed_variables"]
            == ["shutdown_order"],
            next(
                item
                for item in trajectories
                if item["id"] == "TAU_GREG_COUNTERFACTUAL"
            ),
        ),
        check(
            "fork_to_upstream_frame_change_is_explicit",
            "identity_edge_same_author_and_title"
            in next(
                item
                for item in trajectories
                if item["id"] == "TAU_BORIS_OPENCLAW"
            )["nodes"],
            next(
                item
                for item in trajectories
                if item["id"] == "TAU_BORIS_OPENCLAW"
            ),
        ),
    ]

    observer_checks = [
        check(
            "single_observer_for_all_trajectories",
            all(item["observer"] == observer["id"] for item in trajectories),
            [item["observer"] for item in trajectories],
        ),
        check(
            "observer_has_no_state_change_authority",
            causal.get("authority", {}).get("external_state_change") is False
            and causal.get("authority", {}).get("approval") is False
            and causal.get("authority", {}).get("close") is False
            and causal.get("authority", {}).get("merge") is False,
            causal.get("authority"),
        ),
        check(
            "observer_does_not_claim_production_execution",
            greg.get("boundaries", {}).get("production_system_tested") is False
            and greg.get("boundaries", {}).get("third_party_repository_modified")
            is False
            and boris.get("boundaries", {}).get("third_party_state_modified")
            is False,
            {"greg": greg.get("boundaries"), "boris": boris.get("boundaries")},
        ),
    ]

    trajectory_checks = [
        check(
            "greg_endpoint_matches_causal_gate",
            next(
                item
                for item in trajectories
                if item["id"] == "TAU_GREG_COUNTERFACTUAL"
            )["endpoint_classification"]
            in {
                "CONFIRMED_SHUTDOWN_DATA_LOSS_WITH_PASSING_COUNTERFACTUAL",
                "NOT_REPRODUCED_ON_THIS_RUN_STATIC_RISK_REMAINS",
            },
            causal_contract.get("greg"),
        ),
        check(
            "boris_openclaw_endpoint_is_lifecycle_only",
            next(
                item
                for item in trajectories
                if item["id"] == "TAU_BORIS_OPENCLAW"
            )["endpoint_classification"]
            == "CLOSE_AS_SUPERSEDED",
            causal_contract.get("boris_openclaw"),
        ),
        check(
            "boris_claude_endpoint_is_recommendation_only",
            next(
                item
                for item in trajectories
                if item["id"] == "TAU_BORIS_CLAUDE_ISSUES"
            )["endpoint_classification"]
            == "REVIEW_RECOMMENDATIONS_ONLY",
            causal_contract.get("boris_claude_issues"),
        ),
        check(
            "time_orientation_is_forward",
            all(
                parse_time(pair.get("upstream", {}).get("merged_at"))
                < parse_time(boris.get("observed_at"))
                for pair in boris.get("pull_request_pairs", [])
            ),
            [
                pair.get("upstream", {}).get("merged_at")
                for pair in boris.get("pull_request_pairs", [])
            ],
        ),
    ]

    causal_ready = str(causal.get("overall_verdict", "")).startswith(
        "READY_TO_NOTIFY"
    ) and len(causal.get("blocking_checks", [])) == 0

    all_checks = (
        origin_checks + orientation_checks + observer_checks + trajectory_checks
    )
    blocking = [item for item in all_checks if not item["passed"]]

    overall = (
        "OBSERVER_TRAJECTORY_ALIGNED_READY_TO_NOTIFY"
        if causal_ready and not blocking
        else "OBSERVER_TRAJECTORY_MISALIGNED_DO_NOT_NOTIFY"
    )

    result = {
        "schema_version": "liminalqa-observer-trajectory-coordinate-gate-v1",
        "overall_verdict": overall,
        "center_of_orientation": {
            "observer": observer,
            "origins": [greg_origin, boris_origin],
            "axes": {
                "X": "object space: repository, issue, PR, exact source SHA",
                "Y": "state transition: before -> operation or lifecycle change -> after",
                "Z": "execution and authority context",
                "T": "source, merge, correction, and observation time",
                "tau": "ordered evidence trajectory through the declared coordinate frame",
            },
        },
        "trajectories": trajectories,
        "checks": {
            "origin": origin_checks,
            "orientation": orientation_checks,
            "observer": observer_checks,
            "trajectory": trajectory_checks,
        },
        "blocking_checks": blocking,
        "input_hashes": {
            str(greg_path): sha256_file(greg_path),
            str(boris_path): sha256_file(boris_path),
            str(causal_path): sha256_file(causal_path),
        },
        "notification_contract": {
            "permitted": overall == "OBSERVER_TRAJECTORY_ALIGNED_READY_TO_NOTIFY",
            "comments_only": True,
            "state_changes": False,
            "approval": False,
            "close": False,
            "merge": False,
        },
    }

    result_path = output_dir / "observer-trajectory-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    summary = "\n".join(
        [
            "# Center of orientation: observer coordinate trajectory",
            "",
            f"Overall verdict: **{overall}**",
            "",
            "```text",
            "N  = read-only evidence observer",
            "Oᴳ = exact Greg source + issue + isolated runtime + observation time",
            "Oᴮ = exact Boris GitHub resources + current lifecycle observation time",
            "X  = object space",
            "Y  = state transition",
            "Z  = environment and authority context",
            "T  = time",
            "τ  = ordered evidence trajectory",
            "```",
            "",
            f"Blocking checks: `{len(blocking)}`",
            "",
            "External comments are allowed only when both the causal gate and this orientation gate pass. No third-party state mutation is authorized.",
            "",
        ]
    )
    (output_dir / "observer-trajectory-summary.md").write_text(
        summary, encoding="utf-8"
    )

    checksums = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksums.append(f"{sha256_file(path)}  {path.name}")
    (output_dir / "SHA256SUMS.txt").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8"
    )

    print(summary)
    return 1 if blocking or not causal_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
