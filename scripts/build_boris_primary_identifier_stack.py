#!/usr/bin/env python3
"""Build T-Trace, TTM, SDP, DRP, and authority-gate outputs for #21151."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

READY_VERDICT = "READY_TO_NOTIFY_PRIMARY_IDENTIFIER_CONTRACT_SUPPORTED_IMPLEMENTATION_NOT_VERIFIED"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def find_one(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {name}, found {len(matches)}: {matches}")
    return matches[0]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def build_ttrace(matrix: dict[str, Any], observed_at: str, out: Path) -> dict[str, Any]:
    base = parse_time(observed_at)
    records: list[dict[str, Any]] = []
    for index, scenario in enumerate(matrix["scenarios"], start=1):
        thread_id = scenario["scenario_id"]
        sense_ts = base + timedelta(microseconds=index * 10)
        transition_ts = sense_ts + timedelta(microseconds=1)
        commit_ts = transition_ts + timedelta(microseconds=1)
        records.extend(
            [
                {
                    "id": f"{thread_id}-sense",
                    "type": "sense",
                    "ts": iso(sense_ts),
                    "thread_id": thread_id,
                    "input": "collapsed-tool-event",
                    "tool": scenario["tool"],
                    "outcome": scenario["outcome"],
                    "reported_output": scenario["reported_collapsed_model"],
                },
                {
                    "id": f"{thread_id}-transition",
                    "type": "transition",
                    "ts": iso(transition_ts),
                    "thread_id": thread_id,
                    "from": "object_identity_hidden",
                    "to": "primary_identifier_visible",
                    "normalized_identifiers": scenario["normalized_identifiers"],
                    "reference_output": scenario["reference_collapsed_output"],
                },
                {
                    "id": f"{thread_id}-commit",
                    "type": "commit",
                    "ts": iso(commit_ts),
                    "thread_id": thread_id,
                    "confidence": 1.0,
                    "passed": all(scenario["checks"].values()),
                    "checks": scenario["checks"],
                },
            ]
        )
    path = out / "ttrace" / "boris-primary-identifier.ttrace.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n", encoding="utf-8")
    return {"records": len(records), "threads": len(matrix["scenarios"]), "path": str(path)}


def build_ttm(matrix: dict[str, Any], out: Path) -> dict[str, Any]:
    previous = "0" * 64
    records: list[dict[str, Any]] = []
    for scenario in matrix["scenarios"]:
        for sequence, state in enumerate(scenario["lpi_states"], start=1):
            body = {
                "thread_id": scenario["scenario_id"],
                "transition_id": f"{scenario['scenario_id']}:{sequence}",
                "from_state_ref": scenario["lpi_states"][sequence - 2]["state"] if sequence > 1 else None,
                "to_state_ref": state["state"],
                "admissibility": "observed_reference_transition",
                "confidence": 1.0,
                "lane": f"{scenario['tool']}:{scenario['outcome']}:{scenario['cardinality']}",
                "metadata": {
                    "detail": state["detail"],
                    "variant": scenario["variant"],
                    "boundary": "Reference renderer transition; not a Claude Code runtime event.",
                },
                "previous_hash": previous,
            }
            digest = sha256_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            body["seal"] = digest
            previous = digest
            records.append(body)

    path = out / "ttm-db" / "ground-truth.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n", encoding="utf-8")

    errors: list[dict[str, Any]] = []
    replay_previous = "0" * 64
    for index, record in enumerate(records):
        candidate = dict(record)
        seal = candidate.pop("seal")
        if candidate["previous_hash"] != replay_previous:
            errors.append({"index": index, "reason": "previous_hash_mismatch"})
        expected = sha256_bytes(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if expected != seal:
            errors.append({"index": index, "reason": "seal_mismatch"})
        replay_previous = seal
    report = {
        "records": len(records),
        "passed": bool(records) and not errors,
        "errors": errors,
        "chain_head": previous,
        "boundary": "Append-only reference evidence adapter; no production TTM service claim.",
    }
    write_json(out / "ttm-db" / "replay-report.json", report)
    return report


def hypothesis(score: float, status: str, evidence: list[str]) -> dict[str, Any]:
    return {"score": round(score, 3), "status": status, "evidence": evidence}


def build_sdp(evidence: dict[str, Any], out: Path) -> dict[str, Any]:
    signals = evidence["issue_snapshot"]["public_evidence"]["signal_counts"]
    matrix = evidence["matrix_summary"]
    reported_coverage = matrix["reported_model_identifier_coverage"]["passed"]
    reference_coverage = matrix["reference_contract_identifier_coverage"]["passed"]
    total = matrix["reference_contract_identifier_coverage"]["total"]
    critical = matrix["critical_blocked_or_denied_identifier_coverage"]
    ctrl_signal = int(signals.get("ctrl_o_not_sufficient", 0))
    config_signal = int(signals.get("configuration_requested", 0))
    blocked_signal = int(signals.get("blocked_identifier_needed", 0))

    values = {
        "H1_VERBOSE_EXPANSION_IS_SUFFICIENT": hypothesis(
            0.1 if ctrl_signal > 0 else 0.4,
            "not_selected" if ctrl_signal > 0 else "candidate",
            [f"ctrl_o_not_sufficient_signals={ctrl_signal}"],
        ),
        "H2_PRIMARY_IDENTIFIER_MISSING": hypothesis(
            1.0 if reported_coverage < total and reference_coverage == total and critical["passed"] == critical["total"] else 0.3,
            "supported" if reported_coverage < total and reference_coverage == total else "not_selected",
            [
                f"reported_identifier_coverage={reported_coverage}/{total}",
                f"reference_identifier_coverage={reference_coverage}/{total}",
                f"critical_identifier_coverage={critical['passed']}/{critical['total']}",
                f"blocked_identifier_signals={blocked_signal}",
            ],
        ),
        "H3_CONFIGURATION_ONLY": hypothesis(
            0.55 if config_signal > 0 else 0.2,
            "candidate" if config_signal > 0 else "not_selected",
            [
                f"configuration_requested_signals={config_signal}",
                "Security-relevant blocked/denied identity remains a default-contract concern.",
            ],
        ),
        "H4_FULL_DETAILS_ALWAYS_VISIBLE": hypothesis(
            0.25,
            "not_selected",
            ["The tested contract preserves identity while bounding collapsed output to 120 characters."],
        ),
    }
    selected = max(values.items(), key=lambda item: item[1]["score"])[0]
    report = {
        "schema_version": "liminalqa-sdp-primary-identifier-v1",
        "levels": {
            "macro": "Users cannot determine which object a collapsed file-operation event affected.",
            "meso": ["tool event", "collapsed grouping", "outcome", "object identity", "expanded details"],
            "micro": ["tool name", "primary identifier", "cardinality", "blocked/denied state", "path normalization"],
            "pico": ["basename collision", "workspace-relative path", "pattern visibility", "bounded multi-target sample"],
        },
        "hypotheses": values,
        "selected_hypothesis": selected,
        "boundary": "Deterministic advisory collapse over public issue evidence and a disclosed reference renderer.",
    }
    write_json(out / "sdp" / "hypothesis-collapse.json", report)
    return report


def build_drp(verdict: str, evidence: dict[str, Any], out: Path) -> list[dict[str, Any]]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    records = [
        {
            "record_id": "boris-claude-code-21151-review-001",
            "timestamp": "2026-07-20T19:35:38Z",
            "context": "Initial public review found Claude Code #21151 open and recommended defining a collapsed file-operation visibility contract.",
            "decision": "Keep the issue open and define a visible primary-identifier contract.",
            "options": ["Close as implemented", "Keep open without acceptance criteria", "Keep open and define a contract"],
            "status": "complete",
            "rationale": "The public issue described hidden object identity across file-operation tools.",
            "impact": 0,
            "tags": ["boris", "claude-code", "tui", "observability"],
        },
        {
            "record_id": "boris-claude-code-21151-contract-002",
            "timestamp": now,
            "context": "A public-issue snapshot and bounded reference-renderer matrix now define testable collapsed-view acceptance criteria.",
            "decision": (
                "Treat the missing primary identifier as a supported product contract; keep implementation status unverified."
                if verdict == READY_VERDICT
                else "Hold the contract notification until evidence gates pass."
            ),
            "options": [
                "Claim the current product is fixed",
                "Claim source-level root cause",
                "Publish a product contract without implementation claims",
                "Close the issue",
            ],
            "status": "superseded",
            "supersedes_record_id": "boris-claude-code-21151-review-001",
            "parent_record_ids": ["boris-claude-code-21151-review-001"],
            "rationale": verdict,
            "impact": 1 if verdict == READY_VERDICT else 0,
            "tags": ["boris", "claude-code", "primary-identifier", "contract"],
            "metadata": {
                "issue_updated_at": evidence["issue_snapshot"]["updated_at"],
                "matrix_summary": evidence["matrix_summary"],
            },
        },
    ]
    records[0]["child_record_ids"] = ["boris-claude-code-21151-contract-002"]
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
    evidence_path = find_one(input_root, "boris-primary-identifier-evidence-input.json")
    matrix_path = find_one(input_root, "render-matrix.json")
    evidence = load(evidence_path)
    matrix = load(matrix_path)
    contracts = load(Path(args.component_contracts))

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("input_evidence_has_no_blockers", not evidence["blocking_checks"], evidence["blocking_checks"])
    add("component_contracts_pass", contracts.get("passed") is True, contracts)
    add("issue_remains_open", evidence["issue_snapshot"]["state"] == "open", evidence["issue_snapshot"]["state"])
    add("boris_remains_assigned", "bcherny" in evidence["issue_snapshot"]["assignees"], evidence["issue_snapshot"]["assignees"])
    add("reference_renderer_disclosed", matrix.get("boundary", "").startswith("Disclosed reference renderer"), matrix.get("boundary"))
    add("reference_contract_passes", evidence["matrix_summary"]["contract_passed"] is True, evidence["matrix_summary"]["contract_failures"])
    add(
        "reference_identifier_coverage_complete",
        evidence["matrix_summary"]["reference_contract_identifier_coverage"]["passed"]
        == evidence["matrix_summary"]["reference_contract_identifier_coverage"]["total"],
        evidence["matrix_summary"]["reference_contract_identifier_coverage"],
    )
    add(
        "critical_identifier_coverage_complete",
        evidence["matrix_summary"]["critical_blocked_or_denied_identifier_coverage"]["passed"]
        == evidence["matrix_summary"]["critical_blocked_or_denied_identifier_coverage"]["total"],
        evidence["matrix_summary"]["critical_blocked_or_denied_identifier_coverage"],
    )
    add(
        "implementation_claim_forbidden",
        "The current Claude Code implementation was source-audited." in evidence["claim_boundary"]["forbidden"],
        evidence["claim_boundary"],
    )

    preliminary_blocking = [item for item in checks if not item["passed"]]
    preliminary_verdict = READY_VERDICT if not preliminary_blocking else "BLOCKED_PRIMARY_IDENTIFIER_EVIDENCE_INCOMPLETE"
    ttrace = build_ttrace(matrix, evidence["observed_at"], out)
    ttm = build_ttm(matrix, out)
    sdp = build_sdp(evidence, out)
    drp = build_drp(preliminary_verdict, evidence, out)

    add("ttrace_nonempty", ttrace["records"] > 0 and ttrace["threads"] == len(matrix["scenarios"]), ttrace)
    add("ttm_replay_clean", ttm["passed"] is True, ttm)
    add("sdp_selects_primary_identifier", sdp["selected_hypothesis"] == "H2_PRIMARY_IDENTIFIER_MISSING", sdp)
    add("drp_records_present", len(drp) == 2, {"records": len(drp)})

    blocking = [item for item in checks if not item["passed"]]
    verdict = READY_VERDICT if not blocking else "BLOCKED_PRIMARY_IDENTIFIER_EVIDENCE_INCOMPLETE"
    if verdict != preliminary_verdict:
        drp = build_drp(verdict, evidence, out)

    result = {
        "schema_version": "liminalqa-boris-primary-identifier-full-stack-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "target": {
            "repository": evidence["issue_snapshot"]["repository"],
            "issue_number": evidence["issue_snapshot"]["issue_number"],
            "issue_url": evidence["issue_snapshot"]["html_url"],
            "state": evidence["issue_snapshot"]["state"],
            "assignees": evidence["issue_snapshot"]["assignees"],
            "tracker_main_sha": evidence["issue_snapshot"]["tracker_main_sha"],
        },
        "public_evidence": evidence["issue_snapshot"]["public_evidence"],
        "matrix_summary": evidence["matrix_summary"],
        "component_contracts": contracts,
        "checks": checks,
        "blocking_checks": blocking,
        "layers": {
            "lpi": {
                "model": "Hello -> Mirror -> Bind -> Seal -> Flow",
                "application": "tool event -> normalized primary identifier -> collapsed surface -> contract seal -> visible output",
            },
            "capu": {
                "model": "Gate -> Incubate -> Commit -> Execute",
                "application": "blocked or denied file action cannot commit an opaque collapsed message",
            },
            "ttrace": ttrace,
            "ttm_db": ttm,
            "sdp": sdp,
            "drp": {"records": len(drp)},
        },
        "summary": {
            "contract_status": "SUPPORTED" if verdict == READY_VERDICT else "INCOMPLETE",
            "implementation_status": "NOT_VERIFIED",
            "source_audit_status": "NOT_PERFORMED",
            "issue_lifecycle_recommendation": "KEEP_OPEN_PENDING_CURRENT_PRODUCT_VERIFICATION",
        },
        "notification_contract": {
            "permitted": verdict == READY_VERDICT,
            "comments_only": True,
            "state_changes": False,
            "may_claim_public_issue_support": verdict == READY_VERDICT,
            "may_claim_reference_contract_passed": verdict == READY_VERDICT,
            "may_claim_current_product_fixed": False,
            "may_claim_private_tui_source_audited": False,
            "may_close_issue": False,
            "must_disclose_reference_renderer": True,
            "must_disclose_runtime_not_verified": True,
        },
        "input_hashes": {
            "evidence_input_sha256": sha256_file(evidence_path),
            "render_matrix_sha256": sha256_file(matrix_path),
            "component_contracts_sha256": sha256_file(Path(args.component_contracts)),
        },
    }
    write_json(out / "boris-primary-identifier-full-stack-result.json", result)

    summary_lines = [
        "# Boris / Claude Code #21151 full-stack evidence",
        "",
        f"- verdict: **{verdict}**",
        f"- blocking checks: `{len(blocking)}`",
        f"- public comments fetched: `{evidence['issue_snapshot']['public_evidence']['comment_count_fetched']}`",
        f"- unique public authors: `{evidence['issue_snapshot']['public_evidence']['unique_comment_authors']}`",
        f"- reference scenarios: `{evidence['matrix_summary']['total_scenarios']}`",
        f"- reference identifier coverage: `{evidence['matrix_summary']['reference_contract_identifier_coverage']['passed']}/{evidence['matrix_summary']['reference_contract_identifier_coverage']['total']}`",
        f"- critical blocked/denied coverage: `{evidence['matrix_summary']['critical_blocked_or_denied_identifier_coverage']['passed']}/{evidence['matrix_summary']['critical_blocked_or_denied_identifier_coverage']['total']}`",
        f"- T-Trace records: `{ttrace['records']}`",
        f"- TTM records: `{ttm['records']}`",
        f"- TTM replay errors: `{len(ttm['errors'])}`",
        f"- SDP selected: `{sdp['selected_hypothesis']}`",
        "",
        "This packet validates a public product contract and a disclosed reference renderer.",
        "It does not claim access to Claude Code's private TUI source or verification of the current installed runtime.",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")

    checksum_lines: list[str] = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksum_lines.append(f"{sha256_file(path)}  {path.relative_to(out)}")
    (out / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "blocking": len(blocking)}, sort_keys=True))
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
