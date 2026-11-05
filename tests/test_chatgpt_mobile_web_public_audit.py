from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "audits" / "chatgpt" / "mobile-web-public.json"
RESULT_PATH = ROOT / "audits" / "chatgpt" / "mobile-web-public-result.json"
DIAGNOSTIC_PATH = ROOT / "audits" / "chatgpt" / "mobile-web-diagnostics-result.json"
SCRIPT_PATH = ROOT / "scripts" / "chatgpt_mobile_web_public_observer.mjs"
DOC_PATH = ROOT / "docs" / "audits" / "CHATGPT_MOBILE_WEB_PUBLIC_AUDIT.md"


def _config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _result() -> dict:
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def _diagnostic() -> dict:
    return json.loads(DIAGNOSTIC_PATH.read_text(encoding="utf-8"))


def test_target_and_public_boundary_are_exact() -> None:
    config = _config()
    boundaries = config["boundaries"]

    assert config["target_url"] == "https://chatgpt.com/"
    assert config["login_url"] == "https://chatgpt.com/auth/login"
    assert boundaries["public_pages_only"] is True

    forbidden = {
        "authenticated_testing",
        "message_submission",
        "login_submission",
        "file_upload",
        "microphone_permission",
        "camera_permission",
        "direct_application_api_testing",
        "fuzzing",
        "load_testing",
        "active_security_testing",
        "captcha_or_access_control_bypass",
        "private_data_collection",
    }
    for key in forbidden:
        assert boundaries[key] is False


def test_matrix_separates_user_agent_viewport_and_compact_height() -> None:
    config = _config()
    profiles = {profile["id"]: profile for profile in config["profiles"]}

    assert set(profiles) == {
        "desktop-ua-desktop-viewport",
        "desktop-ua-mobile-viewport",
        "mobile-ua-desktop-viewport",
        "mobile-ua-mobile-viewport",
        "mobile-ua-compact-height",
    }
    assert profiles["desktop-ua-mobile-viewport"]["viewport"]["width"] == 412
    assert profiles["mobile-ua-desktop-viewport"]["viewport"]["width"] == 1440
    assert profiles["mobile-ua-compact-height"]["viewport"]["height"] == 520


def test_observer_is_passive_and_does_not_submit_user_content() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "page.goto" in script
    assert "page.screenshot" in script
    assert "message_submission" in script
    assert "login_submission" in script
    assert "captcha_or_access_control_bypass" in script

    prohibited_calls = (
        "page.click(",
        "element.click(",
        "page.type(",
        "keyboard.type(",
        "page.fill(",
        "setRequestInterception",
        "page.authenticate",
    )
    for call in prohibited_calls:
        assert call not in script


def test_final_result_preserves_passes_and_one_diagnostic_only() -> None:
    result = _result()
    observations = {item["id"]: item for item in result["confirmed_observations"]}
    rejected = {item["id"]: item for item in result["rejected_signals"]}

    assert result["verdict"] == "ONE_P3_DIAGNOSTIC_ONLY"
    assert observations["mobile-user-agent-variant"]["status"] == (
        "CONFIRMED_ARCHITECTURE_NOT_DEFECT"
    )
    assert observations["mobile-login-console-error"]["status"] == (
        "CONFIRMED_DIAGNOSTIC_USER_IMPACT_UNKNOWN"
    )
    assert observations["mobile-login-console-error"]["severity"] == "P3-diagnostic"
    assert rejected["mobile-event-post-aborts"]["status"] == (
        "REJECTED_FALSE_NETWORK_FAILURE"
    )
    assert rejected["composer-overlap-detector"]["status"] == (
        "REJECTED_FALSE_POSITIVE"
    )


def test_focused_diagnostic_rejects_event_delivery_false_positive() -> None:
    diagnostic = _diagnostic()
    adjudications = {item["id"]: item for item in diagnostic["adjudications"]}

    assert diagnostic["verdict"] == "ONE_P3_DIAGNOSTIC_ONLY"
    assert adjudications["unauth-mweb-event-aborts"]["status"] == (
        "REJECTED_FALSE_NETWORK_FAILURE"
    )
    assert adjudications["mobile-login-console-error"]["status"] == (
        "CONFIRMED_DIAGNOSTIC_USER_IMPACT_UNKNOWN"
    )
    assert adjudications["mobile-login-console-error"]["evidence"][
        "visible_login_failure"
    ] is False


def test_audit_keeps_signed_out_and_authenticated_claims_separate() -> None:
    document = DOC_PATH.read_text(encoding="utf-8")

    required = {
        "SIGNED_OUT_PUBLIC_EVIDENCE",
        "NEEDS_AUTHENTICATED_MOBILE_EVIDENCE",
        "ONE_P3_DIAGNOSTIC_ONLY",
        "No prompt is submitted",
        "mobile application",
        "mobile web",
        "REJECTED_FALSE_NETWORK_FAILURE",
        "CONFIRMED_DIAGNOSTIC_USER_IMPACT_UNKNOWN",
    }
    for term in required:
        assert term in document
