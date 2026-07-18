#!/usr/bin/env python3
"""Build a deterministic Lotus decision packet from bounded TakeProfit evidence.

The packet combines three advisory readings:

- Pythia: evidence quality, exact-state binding, and explicit uncertainty;
- CML: causal memory across time without turning recurrence into authority;
- LS: user freedom, state visibility, repair, and challengeability.

It never performs an external action or grants approval, execution, delivery, or merge
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "liminalqa-takeprofit-lotus-decision-v1"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def authority_boundary() -> dict[str, Any]:
    return {
        "mode": "advisory_audit_only",
        "grants": {
            "ownership": False,
            "approval": False,
            "execution": False,
            "delivery": False,
            "merge": False,
        },
        "statement": (
            "The Lotus packet explains evidence, memory, uncertainty, and user impact. "
            "It does not authorize testing beyond the declared scope, modify TakeProfit, "
            "submit reports, approve fixes, or execute consequential actions."
        ),
    }


def validate_inputs(
    historical: dict[str, Any],
    portfolio: dict[str, Any],
    chart: dict[str, Any],
    counterfactual: dict[str, Any],
) -> None:
    require(
        historical.get("schema_version")
        == "liminalqa-takeprofit-historical-manual-findings-v1",
        "Unexpected historical findings schema",
    )
    require(
        portfolio.get("schema_version")
        == "liminalqa-takeprofit-lighthouse-portfolio-v1",
        "Unexpected portfolio schema",
    )
    require(
        chart.get("schema_version")
        == "liminalqa-takeprofit-chart-quote-result-v1",
        "Unexpected chart evidence schema",
    )
    require(
        counterfactual.get("schema_version")
        == "liminalqa-takeprofit-stale-quote-counterfactual-result-v1",
        "Unexpected counterfactual schema",
    )

    require(chart.get("target") == counterfactual.get("target"), "Target mismatch")
    require(chart.get("symbol", {}).get("display") == "BTC/USDT", "Unexpected symbol")
    require(portfolio.get("target_count") == 6, "Portfolio must contain six targets")
    require(portfolio.get("warning_count") == 6, "Portfolio evidence is incomplete")

    for name, evidence in (
        ("portfolio", portfolio),
        ("chart", chart),
        ("counterfactual", counterfactual),
    ):
        boundaries = evidence.get("boundaries", {})
        require(bool(boundaries), f"Missing boundaries: {name}")
        for forbidden in (
            "authenticated_testing",
            "api_testing",
            "direct_api_testing",
            "financial_operations",
            "fuzzing",
            "load_testing",
            "vulnerability_claim",
        ):
            if forbidden in boundaries:
                require(boundaries[forbidden] is False, f"Boundary exceeded: {name}.{forbidden}")


def chart_case(
    historical: dict[str, Any], portfolio: dict[str, Any], chart: dict[str, Any]
) -> dict[str, Any]:
    regression = chart["confirmed_regression"]
    historical_ids = [item["id"] for item in historical["findings"]]
    return {
        "id": "TP-CHART-STATE-01",
        "title": "ChartStore initializes from incomplete chart settings",
        "overall_state": "CONFIRMED_REPEATED_FAMILY",
        "severity": {
            "technical": "HIGH",
            "public_user_impact": "MEDIUM",
            "authenticated_workspace_boundary": "P1_CANDIDATE_UNVERIFIED",
        },
        "observation": (
            "The current public BTC/USDT indicator chart renders, but ChartStore logs "
            "missing required settings during initial load and again after reload."
        ),
        "causal_hypothesis": (
            "Default or persisted chart settings are assembled without one versioned, "
            "schema-valid constructor before ChartStore consumers subscribe."
        ),
        "pythia": {
            "verdict": "CONFIRMED",
            "confidence": "HIGH",
            "evidence": [
                regression["signature"],
                "observed_on_initial_load=true",
                "observed_after_reload=true",
                f"portfolio_regression={portfolio['current_regression_signal']['verdict']}",
            ],
            "explicit_uncertainty": [
                "The public chart continued rendering; downstream feature breakage was not demonstrated.",
                "The current run does not prove the authenticated workspace uses the same initialization path.",
                "A shared root implementation across January and July is a hypothesis, not a confirmed cause."
            ],
            "decision": "ESCALATE",
            "reason_codes": [
                "REQUIRED_STATE_SCHEMA_VIOLATION",
                "REPRODUCED_AFTER_RELOAD",
                "AUTHENTICATED_IMPACT_UNVERIFIED",
            ],
        },
        "cml": {
            "memory_state": "REPEATED_FAMILY",
            "historical_observation_ids": historical_ids,
            "current_signature": regression["signature"],
            "linkage": (
                "January reports and the July run contain different missing fields but the "
                "same required-field initialization family on chart state."
            ),
            "confirmed_cause": False,
            "cause_state": "CORRELATED_FAMILY",
            "supersession": (
                "The new signature does not erase the January records. It is stored as a new "
                "revision of the defect family until implementation identity is verified."
            ),
        },
        "ls": {
            "user_control_state": "DEGRADED_BUT_PARTIALLY_HIDDEN",
            "visibility": (
                "The visible chart can imply a clean initialization even while its state contract fails."
            ),
            "choice_and_repair": (
                "The public surface gives the user no diagnostic or repair action for the degraded state."
            ),
            "challengeability": "Console evidence is inspectable; ordinary users do not see it.",
            "human_impact": (
                "Later indicator, drawing, persistence, or reload failures may appear disconnected "
                "from the hidden initialization defect."
            ),
        },
        "minimal_fix": (
            "Create one versioned schema-valid chart-settings constructor, migrate older persisted "
            "objects before ChartStore creation, and fail visibly or repair deterministically before rendering."
        ),
        "regression_test": (
            "Cold load and reload a published chart with persisted and empty settings; assert zero "
            "required-field errors and identical schema-complete ChartStore state before subscribers run."
        ),
    }


def stale_case(chart: dict[str, Any], counterfactual: dict[str, Any]) -> dict[str, Any]:
    classification = counterfactual["classification"]
    checks = classification["checks"]
    stale_supported = checks.get("stale_state_clarity") == "FAIL"
    hold = counterfactual.get("treatment", {}).get("held_response") or {}
    prior = next(item for item in chart["risk_findings"] if item["id"] == "TP-QUOTE-STATE-02")

    evidence_state = "CONFIRMED_REPEATED" if stale_supported else "CONFIRMED_ON_SHORT_INTERRUPTION"
    pythia_verdict = "CONFIRMED" if stale_supported else "ESCALATE"
    confidence = "HIGH" if stale_supported else "MEDIUM"

    return {
        "id": "TP-QUOTE-STATE-02",
        "title": "Last-known quote remains plausible without a freshness boundary",
        "overall_state": evidence_state,
        "severity": {
            "public_surface": "MEDIUM",
            "trading_workspace_boundary": "HIGH_P1_CANDIDATE_UNVERIFIED",
        },
        "observation": prior["evidence"],
        "counterfactual_observation": {
            "hold_achieved": bool(hold),
            "hold_duration_ms": hold.get("hold_duration_ms"),
            "chart_visible_before_release": bool(
                hold.get("states", {}).get("before_release", {}).get("chart_surface_count", 0)
            ),
            "freshness_terms": counterfactual.get("treatment", {}).get(
                "freshness_terms_observed", []
            ),
            "recovery_after_release": checks.get("recovery_after_release"),
        },
        "causal_hypothesis": (
            "The rendered chart retains the last successful state while freshness is tracked, if at all, "
            "outside the user-visible chart status."
        ),
        "pythia": {
            "verdict": pythia_verdict,
            "confidence": confidence,
            "evidence": [
                "Five-second network interruption preserved the chart without an observed stale/offline marker.",
                f"counterfactual_stale_state_clarity={checks.get('stale_state_clarity')}",
                f"counterfactual_hold_duration_ms={hold.get('hold_duration_ms')}",
            ],
            "explicit_uncertainty": [
                "The public indicator card is not the authenticated trading workspace.",
                "No claim is made that a user placed or could place an order from the tested surface.",
                "Canvas rendering does not expose a trustworthy quote timestamp for direct visual age measurement."
            ],
            "decision": "ESCALATE",
            "reason_codes": [
                "LAST_KNOWN_VALUE_REMAINS_VISIBLE",
                "FRESHNESS_BOUNDARY_NOT_OBSERVED",
                "TRADING_CONTEXT_REQUIRES_AUTHORIZED_RETEST",
            ],
        },
        "cml": {
            "memory_state": "REPEATED_BEHAVIOR" if stale_supported else "OBSERVED_ONCE_PLUS_CANDIDATE",
            "linked_runs": [
                chart["run"]["workflow_run_id"],
                counterfactual.get("run", {}).get("workflow_run_id"),
            ],
            "confirmed_cause": False,
            "cause_state": "BEHAVIOR_REPEATED_ROOT_CAUSE_UNCONFIRMED",
            "scope": "public BTC/USDT published-indicator chart",
            "context_boundary": (
                "Do not reuse this finding as proof about authenticated order-entry or other symbols without a scoped retest."
            ),
        },
        "ls": {
            "user_control_state": "INFORMED_CONTROL_REDUCED",
            "visibility": (
                "A plausible retained chart does not disclose whether it is fresh, delayed, reconnecting, or offline."
            ),
            "choice_and_repair": (
                "The user cannot decide whether to wait, refresh, disregard the value, or trust it based on visible state."
            ),
            "challengeability": (
                "Freshness should be inspectable through a last-update timestamp and explicit connection state."
            ),
            "human_impact": (
                "A stale but believable financial value can influence timing, analysis, alerts, and trust more than an obvious blank state."
            ),
        },
        "minimal_fix": (
            "Track last successful symbol-bound market-data time separately from page connectivity and show "
            "fresh, delayed, reconnecting, offline-last-known, and no-data states."
        ),
        "regression_test": (
            "Delay or block quote delivery beyond the expected heartbeat; assert a visible stale/delayed state, "
            "retain the last-known timestamp, and clear the warning only after newer matching-symbol data arrives."
        ),
    }


def ordering_case(counterfactual: dict[str, Any]) -> dict[str, Any]:
    checks = counterfactual["classification"]["checks"]
    treatment = counterfactual["treatment"]
    created = checks.get("out_of_order_transport_delivery") == "CREATED"
    overlap = len(treatment.get("overlapping_quote_responses", []))
    return {
        "id": "TP-QUOTE-ORDER-03",
        "title": "Older quote response may arrive after a newer poll",
        "overall_state": "TRANSPORT_CREATED_APPLICATION_UNVERIFIED" if created else "UNVERIFIED",
        "severity": "HIGH_CANDIDATE" if created else "MEDIUM_CANDIDATE",
        "pythia": {
            "verdict": "ESCALATE",
            "confidence": "MEDIUM" if created else "LOW",
            "evidence": [
                f"natural_overlapping_quote_responses={overlap}",
                f"out_of_order_transport_delivery={checks.get('out_of_order_transport_delivery')}",
            ],
            "explicit_uncertainty": [
                "The public canvas does not expose the applied quote sequence or server timestamp.",
                "An older transport response arriving later does not prove that application state rolled back.",
            ],
            "reason_codes": [
                "APPLICATION_ORDERING_NOT_OBSERVABLE",
                "SEQUENCE_OR_SERVER_TIME_ASSERTION_REQUIRED",
            ],
        },
        "cml": {
            "memory_state": "EXPERIMENTAL_CANDIDATE",
            "confirmed_cause": False,
            "cause_state": "TRANSPORT_CONDITION_ONLY" if created else "NOT_CREATED",
        },
        "ls": {
            "user_control_state": "RISK_NOT_YET_USER_VISIBLE",
            "impact_boundary": (
                "Only a demonstrated visible rollback, mixed symbol state, or inconsistent timestamp would establish user impact."
            ),
        },
        "next_experiment": (
            "Expose or instrument symbol, server timestamp, response sequence, and applied-state sequence; "
            "deliver response A after B and assert A is rejected."
        ),
    }


def build_packet(
    historical_path: Path,
    portfolio_path: Path,
    chart_path: Path,
    counterfactual_path: Path,
) -> dict[str, Any]:
    historical = load_json(historical_path)
    portfolio = load_json(portfolio_path)
    chart = load_json(chart_path)
    counterfactual = load_json(counterfactual_path)
    validate_inputs(historical, portfolio, chart, counterfactual)

    cases = [
        chart_case(historical, portfolio, chart),
        stale_case(chart, counterfactual),
        ordering_case(counterfactual),
    ]
    confirmed = sum(
        1
        for case in cases
        if case["overall_state"].startswith("CONFIRMED")
        or case["overall_state"] == "CONFIRMED_REPEATED_FAMILY"
    )
    packet = {
        "schema_version": SCHEMA_VERSION,
        "target": chart["target"],
        "symbol": chart["symbol"],
        "decision": "ESCALATE",
        "stop_reason": "CONFIRMED_STATE_AMBIGUITY_AND_UNRESOLVED_ORDERING_BOUNDARY",
        "summary": {
            "case_count": len(cases),
            "confirmed_or_repeated_case_count": confirmed,
            "action": (
                "Product review and scoped regression fixes are recommended. Authenticated workspace claims "
                "require separate written authorization and fresh evidence."
            ),
        },
        "lotus_path": [
            "LiminalQA exact evidence",
            "Pythia evidence and uncertainty judgment",
            "CML temporal and cross-run memory",
            "LS user-control impact",
            "human-reviewed decision packet",
        ],
        "cases": cases,
        "evidence": [
            {
                "role": "historical_manual_findings",
                "path": str(historical_path),
                "sha256": sha256(historical_path),
                "provenance": historical["source"]["provenance"],
                "original_attachment_digest_available": historical["source"][
                    "original_attachment_digest_available"
                ],
            },
            {
                "role": "lighthouse_portfolio",
                "path": str(portfolio_path),
                "sha256": sha256(portfolio_path),
                "workflow_run_id": portfolio["run"]["workflow_run_id"],
                "exact_head_sha": portfolio["run"]["exact_head_sha"],
                "artifact_digest": portfolio["run"]["portfolio_artifact_digest"],
            },
            {
                "role": "chart_quote_observation",
                "path": str(chart_path),
                "sha256": sha256(chart_path),
                "workflow_run_id": chart["run"]["workflow_run_id"],
                "exact_head_sha": chart["run"]["exact_head_sha"],
                "artifact_digest": chart["run"]["artifact_digest"],
            },
            {
                "role": "stale_quote_counterfactual",
                "path": str(counterfactual_path),
                "sha256": sha256(counterfactual_path),
                "workflow_run_id": counterfactual.get("run", {}).get("workflow_run_id"),
                "exact_head_sha": counterfactual.get("run", {}).get("exact_head_sha"),
                "artifact_digest": counterfactual.get("run", {}).get("artifact_digest"),
            },
        ],
        "authority": authority_boundary(),
        "limitations": [
            "Public pages only; no authenticated workspace, portfolio, alert, or order-entry testing.",
            "Recurrence supports memory and prioritization but does not prove a shared implementation cause.",
            "A verdict is advisory output and does not submit a report or authorize external action.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return packet


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# TakeProfit Lotus Decision Packet 🌸",
        "",
        f"**Decision:** `{packet['decision']}`  ",
        f"**Stop reason:** `{packet['stop_reason']}`  ",
        f"**Target:** `{packet['target']}`",
        "",
        "## Lotus path",
        "",
        "```text",
        " → ".join(packet["lotus_path"]),
        "```",
        "",
        "## Decision table",
        "",
        "| Case | State | Pythia | CML | LS |",
        "|---|---|---|---|---|",
    ]
    for case in packet["cases"]:
        lines.append(
            "| {id} | {state} | {pythia} | {cml} | {ls} |".format(
                id=case["id"],
                state=case["overall_state"],
                pythia=case["pythia"]["verdict"],
                cml=case["cml"]["memory_state"],
                ls=case["ls"]["user_control_state"],
            )
        )

    for case in packet["cases"]:
        lines.extend(
            [
                "",
                f"## {case['id']} · {case['title']}",
                "",
                f"**State:** `{case['overall_state']}`  ",
                f"**Severity:** `{json.dumps(case['severity'], ensure_ascii=False)}`",
                "",
                "### Pythia",
                "",
                f"- Verdict: `{case['pythia']['verdict']}`",
                f"- Confidence: `{case['pythia']['confidence']}`",
                "- Explicit uncertainty:",
            ]
        )
        for item in case["pythia"].get("explicit_uncertainty", []):
            lines.append(f"  - {item}")
        lines.extend(
            [
                "",
                "### CML",
                "",
                f"- Memory state: `{case['cml']['memory_state']}`",
                f"- Confirmed cause: `{case['cml'].get('confirmed_cause', False)}`",
                "",
                "### LS",
                "",
                f"- User control: `{case['ls']['user_control_state']}`",
            ]
        )
        if case["ls"].get("human_impact"):
            lines.append(f"- Human impact: {case['ls']['human_impact']}")
        if case.get("minimal_fix"):
            lines.extend(["", "### Minimal fix", "", case["minimal_fix"]])
        if case.get("regression_test"):
            lines.extend(["", "### Regression test", "", case["regression_test"]])
        if case.get("next_experiment"):
            lines.extend(["", "### Next experiment", "", case["next_experiment"]])

    lines.extend(
        [
            "",
            "## Evidence binding",
            "",
            "| Role | Workflow run | Exact head | SHA-256 |",
            "|---|---:|---|---|",
        ]
    )
    for evidence in packet["evidence"]:
        lines.append(
            f"| {evidence['role']} | {evidence.get('workflow_run_id') or 'n/a'} | "
            f"{evidence.get('exact_head_sha') or 'n/a'} | `{evidence['sha256']}` |"
        )
    lines.extend(
        [
            "",
            "## Authority boundary",
            "",
            packet["authority"]["statement"],
            "",
            "> Memory is not permission. Verdict is not execution. ESCALATE is not punishment.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_packet(packet: dict[str, Any]) -> None:
    require(packet.get("schema_version") == SCHEMA_VERSION, "Unexpected packet schema")
    require(packet.get("decision") in {"ESCALATE", "BLOCK", "ALLOW"}, "Invalid decision")
    require(packet.get("decision") == "ESCALATE", "This bounded audit must preserve escalation")
    require(len(packet.get("cases", [])) == 3, "Expected exactly three cases")
    grants = packet.get("authority", {}).get("grants", {})
    require(grants and all(value is False for value in grants.values()), "Authority grant detected")
    ids = [case.get("id") for case in packet["cases"]]
    require(len(ids) == len(set(ids)), "Duplicate case identifiers")
    for case in packet["cases"]:
        require(case["pythia"]["verdict"] in {"CONFIRMED", "ESCALATE"}, "Invalid Pythia verdict")
        require(case["cml"].get("confirmed_cause") is False, "Recurrence cannot confirm cause")
        require(bool(case["ls"].get("user_control_state")), "Missing LS user-control state")


def command_build(args: argparse.Namespace) -> int:
    packet = build_packet(
        Path(args.historical),
        Path(args.portfolio),
        Path(args.chart),
        Path(args.counterfactual),
    )
    validate_packet(packet)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "decision-packet.json"
    markdown_path = output / "decision-packet.md"
    json_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(packet), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    packet = load_json(Path(args.packet))
    validate_packet(packet)
    print("Lotus decision packet: PASS")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--historical", required=True)
    build.add_argument("--portfolio", required=True)
    build.add_argument("--chart", required=True)
    build.add_argument("--counterfactual", required=True)
    build.add_argument("--output-dir", required=True)
    build.set_defaults(func=command_build)
    validate = commands.add_parser("validate")
    validate.add_argument("--packet", required=True)
    validate.set_defaults(func=command_validate)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
