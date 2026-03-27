"""
pytest-liminalqa plugin

Hooks into pytest lifecycle and sends test results to the LiminalQA
ingest API via POST /ingest/batch after the session finishes.

Usage:
    pytest --liminalqa-url http://localhost:8080

Or set env vars:
    LIMINALQA_URL=http://localhost:8080
    LIMINALQA_TOKEN=my-secret-token
    LIMINALQA_PLAN=nightly-smoke
"""

from __future__ import annotations

import os
import time
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest


# ---------------------------------------------------------------------------
# ULID generator (no extra dependencies)
# Produces Crockford base32 ULIDs compatible with Rust's `ulid` crate.
# ---------------------------------------------------------------------------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_ulid(n: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(chars))


def _new_ulid() -> str:
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    return _encode_ulid(ms, 10) + _encode_ulid(rand, 16)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------

_CI_PREFIXES = ("CI", "GITHUB_", "GITLAB_CI", "BUILDKITE", "CIRCLE", "TRAVIS", "BUILD_")


class LiminalQAPlugin:
    def __init__(self, url: str, token: Optional[str], plan_name: str) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.plan_name = plan_name

        self.run_id = _new_ulid()
        self.build_id = _new_ulid()
        self.started_at = _now_iso()

        self._tests: List[Dict[str, Any]] = []
        self._start_times: Dict[str, float] = {}

    # -- pytest hooks -------------------------------------------------------

    def pytest_runtest_logstart(self, nodeid: str, location: Any) -> None:
        self._start_times[nodeid] = time.time()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        nodeid = report.nodeid

        # Capture result from "call" phase (actual test body).
        # For skips that happen in "setup" phase, capture those too.
        if report.when == "call":
            status = self._status(report)
            error = self._extract_error(report)
        elif report.when == "setup" and report.skipped:
            status = "skip"
            error = None
        else:
            return

        parts = nodeid.split("::")
        # suite = dotted module path (e.g. "tests.auth.test_login")
        suite = parts[0].replace(os.sep, ".").removesuffix(".py") if parts else "unknown"
        name = "::".join(parts[1:]) if len(parts) > 1 else nodeid

        start = self._start_times.get(nodeid, time.time())
        duration_ms = max(0, int((time.time() - start) * 1000))

        self._tests.append(
            {
                "name": name,
                "suite": suite,
                "status": status,
                "duration_ms": duration_ms,
                "guidance": None,
                "error": error,
                "started_at": None,
                "completed_at": None,
            }
        )

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if not self._tests and not os.environ.get("LIMINALQA_SEND_EMPTY"):
            return
        self._send()

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _status(report: pytest.TestReport) -> str:
        if report.passed:
            return "pass"
        if report.failed:
            return "fail"
        return "skip"

    @staticmethod
    def _extract_error(report: pytest.TestReport) -> Optional[Dict[str, Any]]:
        if not report.failed:
            return None
        longrepr = report.longrepr
        if longrepr is None:
            return None
        message = str(longrepr)[:2000]
        # Detect error type from the last line of the traceback
        error_type = "TestError"
        for line in message.splitlines():
            line = line.strip()
            if line and ":" in line and not line.startswith(("File ", "E ", ">")):
                error_type = line.split(":")[0].strip()
                break
        return {"error_type": error_type, "message": message}

    def _ci_env(self) -> Dict[str, str]:
        return {
            k: v
            for k, v in os.environ.items()
            if any(k.startswith(p) for p in _CI_PREFIXES) and v
        }

    def _build_payload(self) -> Dict[str, Any]:
        return {
            "run": {
                "run_id": self.run_id,
                "build_id": self.build_id,
                "plan_name": self.plan_name,
                "env": self._ci_env(),
                "started_at": self.started_at,
                "runner_version": f"pytest-liminalqa-{__import__('pytest_liminalqa').__version__}",
            },
            "tests": self._tests,
            "signals": [],
            "artifacts": [],
        }

    def _send(self) -> None:
        try:
            import requests  # lazy import — not needed unless URL is set

            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            payload = self._build_payload()
            resp = requests.post(
                f"{self.url}/ingest/batch",
                json=payload,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()

        except Exception as exc:  # noqa: BLE001
            # Telemetry must never crash the test suite
            warnings.warn(
                f"[pytest-liminalqa] Failed to send results to {self.url}: {exc}",
                stacklevel=1,
            )


# ---------------------------------------------------------------------------
# pytest hooks (module-level, registered before session start)
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("liminalqa", "LiminalQA test intelligence")
    group.addoption(
        "--liminalqa-url",
        default=os.environ.get("LIMINALQA_URL", ""),
        metavar="URL",
        help="LiminalQA ingest server URL. Also reads LIMINALQA_URL env var.",
    )
    group.addoption(
        "--liminalqa-token",
        default=os.environ.get("LIMINALQA_TOKEN", ""),
        metavar="TOKEN",
        help="Bearer auth token. Also reads LIMINALQA_TOKEN env var.",
    )
    group.addoption(
        "--liminalqa-plan",
        default=os.environ.get("LIMINALQA_PLAN", "pytest-session"),
        metavar="PLAN",
        help="Plan/suite name for this run. Also reads LIMINALQA_PLAN env var.",
    )


def pytest_configure(config: pytest.Config) -> None:
    url: str = config.getoption("--liminalqa-url", default="")
    if not url:
        return  # disabled — no URL configured

    token_raw: str = config.getoption("--liminalqa-token", default="")
    token: Optional[str] = token_raw if token_raw else None
    plan: str = config.getoption("--liminalqa-plan", default="pytest-session")

    plugin = LiminalQAPlugin(url=url, token=token, plan_name=plan)
    config.pluginmanager.register(plugin, "liminalqa-plugin")
