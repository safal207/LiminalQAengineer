"""
Tests for pytest-liminalqa plugin.

Uses pytest's built-in `pytester` fixture to run sub-pytest processes in
isolated temp directories. The ingest API is mocked with requests-mock.
"""

from __future__ import annotations

import json
import re

import pytest
import requests_mock as req_mock_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _assert_ulid(value: str) -> None:
    assert ULID_RE.match(value), f"Not a valid ULID: {value!r}"


# ---------------------------------------------------------------------------
# ULID generator unit tests
# ---------------------------------------------------------------------------


def test_new_ulid_format() -> None:
    from pytest_liminalqa.plugin import _new_ulid

    ulid = _new_ulid()
    assert len(ulid) == 26
    _assert_ulid(ulid)


def test_new_ulid_uniqueness() -> None:
    from pytest_liminalqa.plugin import _new_ulid

    ulids = {_new_ulid() for _ in range(50)}
    assert len(ulids) == 50


# ---------------------------------------------------------------------------
# _extract_error
# ---------------------------------------------------------------------------


def test_extract_error_on_passing_report() -> None:
    from pytest_liminalqa.plugin import LiminalQAPlugin

    class FakeReport:
        failed = False
        longrepr = None

    result = LiminalQAPlugin._extract_error(FakeReport())  # type: ignore[arg-type]
    assert result is None


def test_extract_error_on_failed_report() -> None:
    from pytest_liminalqa.plugin import LiminalQAPlugin

    class FakeReport:
        failed = True
        longrepr = "AssertionError: assert 1 == 2"

    result = LiminalQAPlugin._extract_error(FakeReport())  # type: ignore[arg-type]
    assert result is not None
    assert "message" in result
    assert "assert 1 == 2" in result["message"]


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------


def test_build_payload_structure() -> None:
    from pytest_liminalqa.plugin import LiminalQAPlugin

    plugin = LiminalQAPlugin(url="http://localhost:8080", token="tok", plan_name="smoke")
    plugin._tests = [
        {
            "name": "test_foo",
            "suite": "tests.test_bar",
            "status": "pass",
            "duration_ms": 42,
            "guidance": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
        }
    ]
    payload = plugin._build_payload()

    assert "run" in payload
    assert "tests" in payload
    assert "signals" in payload
    assert "artifacts" in payload

    run = payload["run"]
    _assert_ulid(run["run_id"])
    _assert_ulid(run["build_id"])
    assert run["plan_name"] == "smoke"
    assert run["runner_version"].startswith("pytest-liminalqa-")

    assert payload["tests"][0]["name"] == "test_foo"
    assert payload["tests"][0]["status"] == "pass"
    assert payload["signals"] == []
    assert payload["artifacts"] == []


# ---------------------------------------------------------------------------
# Integration: plugin sends batch payload via pytester
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_server(requests_mock):
    """Mock the LiminalQA ingest server."""
    requests_mock.post(
        "http://fake-liminalqa/ingest/batch",
        json={"ok": True, "message": "ok", "counts": {"run": 1, "tests": 1, "signals": 0, "artifacts": 0}},
    )
    return requests_mock


def test_plugin_sends_results_for_passing_test(pytester, fake_server):
    pytester.makepyfile("""
        def test_always_passes():
            assert 1 + 1 == 2
    """)

    result = pytester.runpytest(
        "--liminalqa-url=http://fake-liminalqa",
        "--liminalqa-plan=ci-smoke",
        "-v",
    )
    result.assert_outcomes(passed=1)

    assert fake_server.called, "Plugin should have POSTed to /ingest/batch"
    body = fake_server.last_request.json()

    assert body["run"]["plan_name"] == "ci-smoke"
    _assert_ulid(body["run"]["run_id"])

    assert len(body["tests"]) == 1
    test = body["tests"][0]
    assert test["name"] == "test_always_passes"
    assert test["status"] == "pass"
    assert test["duration_ms"] >= 0


def test_plugin_sends_fail_status(pytester, fake_server):
    pytester.makepyfile("""
        def test_always_fails():
            assert False, "expected failure"
    """)

    result = pytester.runpytest(
        "--liminalqa-url=http://fake-liminalqa",
        "-v",
    )
    result.assert_outcomes(failed=1)

    body = fake_server.last_request.json()
    test = body["tests"][0]
    assert test["status"] == "fail"
    assert test["error"] is not None
    assert "expected failure" in test["error"]["message"]


def test_plugin_sends_skip_status(pytester, fake_server):
    pytester.makepyfile("""
        import pytest

        @pytest.mark.skip(reason="not implemented yet")
        def test_skipped():
            pass
    """)

    result = pytester.runpytest(
        "--liminalqa-url=http://fake-liminalqa",
        "-v",
    )
    result.assert_outcomes(skipped=1)

    body = fake_server.last_request.json()
    test = body["tests"][0]
    assert test["status"] == "skip"


def test_plugin_sends_multiple_tests(pytester, fake_server):
    pytester.makepyfile("""
        import pytest

        def test_a():
            assert True

        def test_b():
            assert False

        @pytest.mark.skip
        def test_c():
            pass
    """)

    result = pytester.runpytest(
        "--liminalqa-url=http://fake-liminalqa",
        "-v",
    )
    result.assert_outcomes(passed=1, failed=1, skipped=1)

    body = fake_server.last_request.json()
    assert len(body["tests"]) == 3

    statuses = {t["name"]: t["status"] for t in body["tests"]}
    assert statuses["test_a"] == "pass"
    assert statuses["test_b"] == "fail"
    assert statuses["test_c"] == "skip"


def test_plugin_sends_bearer_token(pytester, fake_server):
    pytester.makepyfile("def test_ok(): pass")

    pytester.runpytest(
        "--liminalqa-url=http://fake-liminalqa",
        "--liminalqa-token=super-secret",
        "-v",
    )

    auth = fake_server.last_request.headers.get("Authorization", "")
    assert auth == "Bearer super-secret"


def test_plugin_disabled_without_url(pytester):
    """Plugin should not register or POST when no URL is given."""
    pytester.makepyfile("def test_ok(): pass")

    # requests_mock not used — if a request is made it would raise
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)
    # If we got here without error, no HTTP call was made


def test_plugin_does_not_fail_on_server_error(pytester, requests_mock):
    """Network failures must not crash the test suite."""
    requests_mock.post(
        "http://fake-liminalqa/ingest/batch",
        status_code=500,
        json={"error": "server error"},
    )
    pytester.makepyfile("def test_ok(): pass")

    result = pytester.runpytest(
        "--liminalqa-url=http://fake-liminalqa",
        "-v",
    )
    # Test suite outcome must not be affected
    result.assert_outcomes(passed=1)


def test_suite_field_uses_dotted_module_path(pytester, fake_server):
    pytester.makepyfile("""
        def test_something():
            pass
    """)

    pytester.runpytest("--liminalqa-url=http://fake-liminalqa", "-v")

    body = fake_server.last_request.json()
    # suite should be a dotted path, not contain .py
    suite = body["tests"][0]["suite"]
    assert ".py" not in suite
