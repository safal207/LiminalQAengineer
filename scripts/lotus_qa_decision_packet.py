#!/usr/bin/env python3
"""Generate a deterministic Lotus Decision Packet from bounded LiminalQA findings."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EVIDENCE_ESCALATE = {"missing", "stale", "conflicting", "inaccessible", "provenance_unverified"}
SUPPORT_ALLOW = {"observed", "counterfactual_supported"}
SUPPORT_BLOCK = {"contradicted", "overstated"}
COUNTERFACTUAL_ESCALATE = {"INCONCLUSIVE", "UNKNOWN"}
COUNTERFACTUAL_BLOCK = {"NOT_SUPPORTED"}
RECURRING = {"repeated", "changed_form", "cross_surface"}

RISK_WEIGHT = {
    "clear": 0,
    "available": 0,
    "none": 0,
    "n_a": 0,
    "degraded": 1,
    "absent": 1,
    "unclear": 1,
    "possible": 1,
    "unknown": 1,
    "hidden": 2,
    "stale": 2,
    "impossible": 2,
    "high": 2,
    "misleading": 2,
}

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "UNASSIGNED": 9}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def require_string(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != "liminalqa-lotus-qa-contract-v0.1":
        raise ValueError("unsupported Lotus QA contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or authority.get("mode") != "audit_only":
        raise ValueError("authority.mode must be audit_only")
    for grant in ("ownership", "approval", "execution", "delivery", "deployment", "merge"):
        if authority.get(grant) is not False:
            raise ValueError(f"authority.{grant} must be false")
    sources = contract.get("source_contracts")
    if not isinstance(sources, dict) or set(sources) != {"pythia", "cml", "ls"}:
        raise ValueError("source_contracts must pin pythia, cml, and ls")
    for name, source in sources.items():
        if not isinstance(source, dict):
            raise ValueError(f"source_contracts.{name} must be an object")
        for key in ("repository", "commit", "path", "blob_sha", "rule"):
            require_string(source, key, f"source_contracts.{name}")


def validate_finding(finding: dict[str, Any]) -> None:
    fid = require_string(finding, "id", "finding")
    for key in ("title", "domain", "surface", "claim_kind", "claim", "severity_candidate", "minimal_fix", "regression_test"):
        require_string(finding, key, fid)
    evidence = finding.get("evidence")
    memory = finding.get("causal_memory")
    control = finding.get("user_control")
    expected = finding.get("expected")
    if not all(isinstance(value, dict) for value in (evidence, memory, control, expected)):
        raise ValueError(f"{fid} requires evidence, causal_memory, user_control, and expected objects")
    for key in ("state", "claim_support", "source_path"):
        require_string(evidence, key, f"{fid}.evidence")
    if evidence.get("bounded") is not True or evidence.get("replayable") is not True:
        raise ValueError(f"{fid} evidence must be bounded and replayable")
    for key in ("canonical_id", "repository_scope", "surface_scope", "state_scope", "time_scope", "recurrence", "human_review"):
        require_string(memory, key, f"{fid}.causal_memory")
    for key in ("evidence_level", "state_visibility", "timeliness", "action_reversibility", "duplicate_action_risk", "error_explainability", "live_historical_clarity", "user_effect"):
        require_string(control, key, f"{fid}.user_control")


def pythia_verdict(finding: dict[str, Any]) -> tuple[str, list[str]]:
    evidence = finding["evidence"]
    reasons: list[str] = []
    state = evidence["state"]
    support = evidence["claim_support"]
    counterfactual = evidence.get("counterfactual") or {}
    counterfactual_status = counterfactual.get("status")

    if state in EVIDENCE_ESCALATE:
        reasons.append(f"evidence_state.{state}")
    if counterfactual_status in COUNTERFACTUAL_ESCALATE:
        reasons.append(f"counterfactual.{counterfactual_status.lower()}")
    if support == "unknown":
        reasons.append("claim_support.unknown")
    if reasons:
        return "ESCALATE", sorted(set(reasons))

    if support in SUPPORT_BLOCK or counterfactual_status in COUNTERFACTUAL_BLOCK:
        if support in SUPPORT_BLOCK:
            reasons.append(f"claim_support.{support}")
        if counterfactual_status in COUNTERFACTUAL_BLOCK:
            reasons.append(f"counterfactual.{counterfactual_status.lower()}")
        return "BLOCK", sorted(set(reasons))

    if state == "exact" and evidence["bounded"] and evidence["replayable"] and support in SUPPORT_ALLOW:
        return "ALLOW", ["exact_bounded_replayable_evidence", f"claim_support.{support}"]

    return "ESCALATE", ["decision_contract_not_satisfied"]


def cml_status(finding: dict[str, Any], pythia: str) -> tuple[str, list[str]]:
    memory = finding["causal_memory"]
    recurrence = memory["recurrence"]
    human_review = memory["human_review"]
    if pythia == "BLOCK":
        return "NEGATIVE_CAUSAL_MEMORY", ["rejected causal hypothesis is preserved as a reviewed lesson candidate"]
    if recurrence == "conflict" or pythia == "ESCALATE":
        return "CONFLICT", ["conflicting or incomplete evidence must not silently supersede prior memory"]
    if human_review == "accepted":
        return "ACCEPTED", ["explicit human review accepted the bounded memory"]
    if recurrence in RECURRING:
        return "PROPOSED_RECURRING", [f"recurrence.{recurrence}", "human_review.pending"]
    return "PROPOSED_SINGLE", ["single bounded observation", "human_review.pending"]


def ls_risk(finding: dict[str, Any]) -> tuple[str, int | None, list[str]]:
    control = finding["user_control"]
    if control["evidence_level"] == "unknown":
        return "UNKNOWN", None, ["user impact was not directly established"]
    keys = (
        "state_visibility",
        "timeliness",
        "action_reversibility",
        "duplicate_action_risk",
        "error_explainability",
        "live_historical_clarity",
    )
    score = 0
    reasons: list[str] = []
    for key in keys:
        value = control[key]
        if value not in RISK_WEIGHT:
            raise ValueError(f"{finding['id']}.user_control.{key} has unsupported value {value!r}")
        weight = RISK_WEIGHT[value]
        score += weight
        if weight:
            reasons.append(f"{key}.{value}")
    if score == 0:
        level = "NONE"
    elif score <= 2:
        level = "LOW"
    elif score <= 5:
        level = "MEDIUM"
    elif score <= 8:
        level = "HIGH"
    else:
        level = "CRITICAL"
    return level, score, reasons or ["no user-control degradation assigned"]


def unified_status(pythia: str) -> str:
    return {"ALLOW": "CONFIRMED", "BLOCK": "BLOCKED", "ESCALATE": "NEEDS_EVIDENCE"}[pythia]


def evaluate_finding(finding: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
    validate_finding(finding)
    pythia, pythia_reasons = pythia_verdict(finding)
    cml, cml_reasons = cml_status(finding, pythia)
    ls, ls_score, ls_reasons = ls_risk(finding)
    unified = unified_status(pythia)
    expected = finding["expected"]
    actual = {"pythia": pythia, "cml": cml, "ls": ls, "unified": unified}
    if actual != expected:
        raise ValueError(f"{finding['id']} expected {expected}, derived {actual}")

    severity = finding["severity_candidate"] if unified == "CONFIRMED" else "UNASSIGNED"
    packet = {
        "finding_id": finding["id"],
        "title": finding["title"],
        "domain": finding["domain"],
        "surface": finding["surface"],
        "claim_kind": finding["claim_kind"],
        "claim": finding["claim"],
        "judgment": {
            "proposed_action": "publish the bounded claim as a confirmed QA finding",
            "verdict": pythia,
            "reasons": pythia_reasons,
            "publishable_as_confirmed": pythia == "ALLOW",
        },
        "causal_memory": {
            "canonical_id": finding["causal_memory"]["canonical_id"],
            "status": cml,
            "reasons": cml_reasons,
            "repository_scope": finding["causal_memory"]["repository_scope"],
            "surface_scope": finding["causal_memory"]["surface_scope"],
            "state_scope": finding["causal_memory"]["state_scope"],
            "time_scope": finding["causal_memory"]["time_scope"],
            "recurrence": finding["causal_memory"]["recurrence"],
            "durable_memory": cml == "ACCEPTED",
        },
        "user_control": {
            "risk": ls,
            "score": ls_score,
            "reasons": ls_reasons,
            "evidence_level": finding["user_control"]["evidence_level"],
            "user_effect": finding["user_control"]["user_effect"],
        },
        "decision": {
            "status": unified,
            "confidence": "HIGH" if pythia == "ALLOW" and finding["evidence"]["state"] == "exact" else "LOW" if pythia == "ESCALATE" else "MEDIUM",
            "severity": severity,
            "severity_candidate": finding["severity_candidate"],
            "human_review_required": True,
            "minimal_fix": finding["minimal_fix"],
            "regression_test": finding["regression_test"],
        },
        "evidence": finding["evidence"],
        "authority": authority,
    }
    packet["packet_sha256"] = sha256_json(packet)
    return packet


def build_packet(contract: dict[str, Any], findings_doc: dict[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    if findings_doc.get("schema_version") != "liminalqa-lotus-findings-v0.1":
        raise ValueError("unsupported findings schema")
    findings = findings_doc.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ValueError("findings must be a non-empty list")
    ids = [f.get("id") for f in findings if isinstance(f, dict)]
    if len(ids) != len(set(ids)):
        raise ValueError("finding ids must be unique")

    evaluated = [evaluate_finding(f, contract["authority"]) for f in findings]
    evaluated.sort(key=lambda item: item["finding_id"])
    verdict_counts = Counter(item["judgment"]["verdict"] for item in evaluated)
    status_counts = Counter(item["decision"]["status"] for item in evaluated)
    risk_counts = Counter(item["user_control"]["risk"] for item in evaluated)

    confirmed = sorted(
        (item for item in evaluated if item["decision"]["status"] == "CONFIRMED"),
        key=lambda item: (SEVERITY_ORDER[item["decision"]["severity"]], item["finding_id"]),
    )
    packet = {
        "schema_version": "liminalqa-lotus-decision-packet-v0.1",
        "packet_id": findings_doc["packet_id"],
        "repository": findings_doc["repository"],
        "source_branch": findings_doc["source_branch"],
        "scope": findings_doc["scope"],
        "contract": {
            "schema_version": contract["schema_version"],
            "sha256": sha256_json(contract),
            "source_contracts": contract["source_contracts"],
        },
        "summary": {
            "finding_count": len(evaluated),
            "pythia_verdicts": dict(sorted(verdict_counts.items())),
            "decision_statuses": dict(sorted(status_counts.items())),
            "user_control_risks": dict(sorted(risk_counts.items())),
            "durable_memory_count": sum(1 for item in evaluated if item["causal_memory"]["durable_memory"]),
            "confirmed_priority": [item["finding_id"] for item in confirmed],
            "escalation_queue": [item["finding_id"] for item in evaluated if item["decision"]["status"] == "NEEDS_EVIDENCE"],
            "blocked_claims": [item["finding_id"] for item in evaluated if item["decision"]["status"] == "BLOCKED"],
        },
        "findings": evaluated,
        "authority": contract["authority"],
        "limitations": [
            "The packet audits supplied materialized evidence; it does not independently fetch or attest remote repositories.",
            "ALLOW means the bounded claim may be published as confirmed under this contract; it is not execution, approval, deployment, or merge authority.",
            "CML memory remains proposed until explicit human review accepts it.",
            "LS user-control risk is UNKNOWN when user-visible impact was not directly established.",
            "Public passive evidence does not establish authenticated trading, model, billing, or security behavior."
        ],
    }
    packet["packet_sha256"] = sha256_json(packet)
    return packet


def render_markdown(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# LiminalQA Lotus Decision Packet v0.1",
        "",
        f"**Packet:** `{packet['packet_id']}`  ",
        f"**Findings:** {summary['finding_count']}  ",
        f"**Packet SHA-256:** `{packet['packet_sha256']}`  ",
        "**Authority:** `audit_only`; ownership, approval, execution, delivery, deployment, and merge grants are all false.",
        "",
        "## Flow",
        "",
        "```text",
        "LiminalQA signal",
        "→ Pythia: evidence-backed ALLOW / BLOCK / ESCALATE",
        "→ CML: scoped causal memory, recurrence, conflict, supersession",
        "→ LS: user visibility, timeliness, reversibility, and control risk",
        "→ unified Lotus Decision Packet",
        "```",
        "",
        "## Summary",
        "",
        f"- Pythia: `{summary['pythia_verdicts']}`",
        f"- Unified: `{summary['decision_statuses']}`",
        f"- User-control risk: `{summary['user_control_risks']}`",
        f"- Durable accepted memories: **{summary['durable_memory_count']}** — all current memories remain proposals pending human review.",
        "",
        "## Findings",
        "",
        "| ID | Domain | Pythia | CML | LS risk | Status | Severity |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in packet["findings"]:
        lines.append(
            f"| `{item['finding_id']}` | {item['domain']} | {item['judgment']['verdict']} | "
            f"{item['causal_memory']['status']} | {item['user_control']['risk']} | "
            f"{item['decision']['status']} | {item['decision']['severity']} |"
        )
    lines.extend(["", "## Priority", ""])
    lines.append("Confirmed: " + (", ".join(f"`{v}`" for v in summary["confirmed_priority"]) or "none"))
    lines.append("")
    lines.append("Escalate: " + (", ".join(f"`{v}`" for v in summary["escalation_queue"]) or "none"))
    lines.append("")
    lines.append("Blocked claims: " + (", ".join(f"`{v}`" for v in summary["blocked_claims"]) or "none"))
    lines.extend(["", "## Lotus boundary", ""])
    lines.append("> The packet can guide review, but it cannot approve, execute, deliver, deploy, or merge anything.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    contract = load_json(args.contract)
    findings = load_json(args.findings)
    packet = build_packet(contract, findings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "lotus-decision-packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "lotus-decision-packet.md").write_text(render_markdown(packet), encoding="utf-8")
    print(render_markdown(packet))


if __name__ == "__main__":
    main()
