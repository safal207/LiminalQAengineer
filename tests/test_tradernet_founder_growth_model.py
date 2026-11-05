from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "audits" / "tradernet" / "founder-growth-model-v1.json"
MEMO_PATH = ROOT / "docs" / "audits" / "TRADERNET_FOUNDER_GROWTH_MEMO.md"


def _model() -> dict:
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def test_growth_model_is_advisory_and_not_a_forecast() -> None:
    authority = _model()["authority"]

    assert authority["mode"] == "advisory_only"
    assert authority["forecast"] is False
    assert authority["investment_advice"] is False
    assert authority["experiment_launch"] is False
    assert authority["account_access"] is False
    assert authority["order_execution"] is False
    assert authority["external_submission"] is False
    assert authority["deployment"] is False
    assert authority["merge"] is False


def test_funnel_math_is_internally_consistent() -> None:
    model = _model()
    stages = {item["id"]: item for item in model["illustrative_monthly_funnel"]["stages"]}

    assert stages["signup"]["current_count"] == 100000 * 0.04
    assert stages["signup"]["target_count"] == 100000 * 0.055
    assert stages["kyc_approved"]["current_count"] == 4000 * 0.45
    assert stages["kyc_approved"]["target_count"] == 5500 * 0.60
    assert stages["funded"]["current_count"] == 1800 * 0.35
    assert stages["funded"]["target_count"] == 3300 * 0.45
    assert stages["first_intentional_action"]["current_count"] == 630 * 0.50
    assert stages["first_intentional_action"]["target_count"] == 1485 * 0.60
    assert model["illustrative_monthly_funnel"]["incremental_activated_funded_users"] == 576


def test_gross_contribution_sensitivity_matches_incremental_users() -> None:
    model = _model()
    incremental = model["illustrative_monthly_funnel"]["incremental_activated_funded_users"]

    for scenario in model["gross_contribution_sensitivity"]:
        monthly = incremental * scenario["monthly_contribution_per_incremental_user_eur"]
        assert scenario["monthly_uplift_eur"] == monthly
        assert scenario["annualised_uplift_eur"] == monthly * 12


def test_plf_and_clickfunnels_reject_financial_pressure() -> None:
    model = _model()
    cf = model["clickfunnels_boundary"]
    plf = model["plf_launch"]

    assert cf["role"] == "pattern_reference_only"
    assert cf["false_urgency"] is False
    assert cf["artificial_scarcity"] is False
    assert cf["pressure_to_trade"] is False
    assert cf["preselected_paid_or_risk_increasing_choices"] is False
    assert cf["vendor_claims_are_subject_evidence"] is False

    assert plf["promise_of_returns"] is False
    assert plf["permanent_education_or_demo_path"] is True
    assert "market_movement_fomo" in plf["forbidden_scarcity"]
    assert "promised_returns" in plf["forbidden_scarcity"]


def test_memo_preserves_scenario_and_evidence_language() -> None:
    memo = MEMO_PATH.read_text(encoding="utf-8")

    required = {
        "Weekly Completed Investor Intent Loops",
        "scenario sensitivities, not forecasts",
        "comprehension before commitment",
        "authorised exact-build test account",
        "Build less pressure. Orchestrate more trust and value.",
    }
    for phrase in required:
        assert phrase in memo


def test_exact_source_audit_is_pinned() -> None:
    source = _model()["source_audit"]

    assert source["repository"] == "safal207/LiminalQAengineer"
    assert source["pull_request"] == 102
    assert source["exact_head"] == "d14d0e0cf434000c10609dc8627c288df5306df6"
