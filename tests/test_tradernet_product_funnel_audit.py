from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = ROOT / "audits" / "tradernet" / "product-funnel-audit-v1.json"
AUDIT_DOC = ROOT / "docs" / "audits" / "TRADERNET_PRODUCT_FUNNEL_AUDIT.md"
BACKLOG_DOC = ROOT / "docs" / "audits" / "TRADERNET_PRODUCT_BACKLOG.md"


def _load_packet() -> dict:
    return json.loads(AUDIT_JSON.read_text(encoding="utf-8"))


def test_product_audit_packet_preserves_authority_boundary() -> None:
    packet = _load_packet()
    authority = packet["authority"]

    assert authority["mode"] == "audit_only"
    assert authority["private_account_access"] is False
    assert authority["order_execution"] is False
    assert authority["external_submission"] is False
    assert authority["pricing_authority"] is False
    assert authority["experiment_authority"] is False
    assert authority["deployment_authority"] is False
    assert authority["merge_authority"] is False


def test_confirmed_findings_are_separate_from_product_hypotheses() -> None:
    packet = _load_packet()
    confirmed = packet["confirmed_findings"]
    hypotheses = packet["product_hypotheses"]

    assert confirmed
    assert hypotheses
    assert all(item["status"] == "CONFIRMED" for item in confirmed)
    assert all(
        item["status"] in {"HYPOTHESIS", "NEEDS_AUTHENTICATED_EVIDENCE"}
        for item in hypotheses
    )

    confirmed_ids = {item["id"] for item in confirmed}
    hypothesis_ids = {item["id"] for item in hypotheses}
    assert confirmed_ids.isdisjoint(hypothesis_ids)


def test_every_product_hypothesis_has_a_bounded_next_test() -> None:
    packet = _load_packet()

    for item in packet["product_hypotheses"]:
        assert item["priority"] in {"P0", "P1", "P2"}
        assert item["next_test"].strip()


def test_clickfunnels_is_pattern_reference_not_subject_evidence() -> None:
    packet = _load_packet()
    clickfunnels = packet["method"]["clickfunnels"]

    assert clickfunnels["use"] == "pattern_reference_only"
    assert clickfunnels["claims_are_subject_evidence"] is False
    assert "false_urgency" in clickfunnels["excluded_patterns"]
    assert "pressure_to_trade" in clickfunnels["excluded_patterns"]


def test_product_docs_keep_evidence_and_human_review_language() -> None:
    audit = AUDIT_DOC.read_text(encoding="utf-8")
    backlog = BACKLOG_DOC.read_text(encoding="utf-8")

    required_audit_terms = {
        "CONFIRMED",
        "HYPOTHESIS",
        "NEEDS_AUTHENTICATED_EVIDENCE",
        "HUMAN_REVIEW_REQUIRED",
        "false countdowns",
        "qualified seven-day activation",
    }
    for term in required_audit_terms:
        assert term in audit

    required_backlog_terms = {
        "Exact build",
        "User impact",
        "Acceptance criteria",
        "Guardrails",
        "No audit label is treated as approval",
    }
    for term in required_backlog_terms:
        assert term in backlog


def test_packet_keeps_lotus_exact_head_and_guardrails() -> None:
    packet = _load_packet()
    lens = packet["method"]["lotus_product_lens"]

    assert lens["repository"] == "safal207/LS"
    assert lens["pull_request"] == 920
    assert lens["exact_head"] == "44087899bdaad86b32b13d89812cbf7a174db2fe"
    assert packet["guardrails"]
    assert packet["verdict"] == "HUMAN_REVIEW_REQUIRED"
