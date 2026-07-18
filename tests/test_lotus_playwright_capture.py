from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lotus_playwright_capture.py"
SPEC = importlib.util.spec_from_file_location("lotus_playwright_capture", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

PROFILE = ROOT / "integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json"
TEMPLATE = ROOT / "integrations/lotus/examples/airbnb-run-002.capture.json"


class LotusPlaywrightCaptureTests(unittest.TestCase):
    def test_plan_does_not_import_browser_or_touch_target(self) -> None:
        value = runner.plan(Namespace(profile=PROFILE, capture_template=TEMPLATE))
        self.assertFalse(value["browser_imported"])
        self.assertFalse(value["target_interaction"])
        self.assertFalse(value["confirmed_defect"])

    def test_url_allowlist_rejects_lookalike_and_credentials(self) -> None:
        self.assertEqual(
            runner.validate_listing_url("https://www.airbnb.com/rooms/123"),
            "https://www.airbnb.com/rooms/123",
        )
        with self.assertRaisesRegex(runner.RunnerError, "not allowlisted"):
            runner.validate_listing_url("https://airbnb.com.evil.example/rooms/123")
        with self.assertRaisesRegex(runner.RunnerError, "credentials"):
            runner.validate_listing_url("https://user:pass@airbnb.com/rooms/123")

    def test_dangerous_submission_requests_are_detected(self) -> None:
        self.assertTrue(
            runner.is_dangerous_request(
                "POST", "https://www.airbnb.com/api/v1/payments/submit"
            )
        )
        self.assertTrue(
            runner.is_dangerous_request(
                "PATCH", "https://www.airbnb.com/checkout/confirm"
            )
        )
        self.assertFalse(
            runner.is_dangerous_request(
                "GET", "https://www.airbnb.com/api/v1/payments/preview"
            )
        )
        self.assertFalse(
            runner.is_dangerous_request(
                "POST", "https://www.airbnb.com/api/v1/search"
            )
        )

    def test_har_redaction_removes_sensitive_values_and_raw_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "raw.har"
            target = root / "redacted.har"
            source.write_text(
                json.dumps(
                    {
                        "log": {
                            "entries": [
                                {
                                    "request": {
                                        "headers": [
                                            {"name": "Cookie", "value": "session=secret"},
                                            {"name": "Authorization", "value": "Bearer abc"},
                                        ],
                                        "cookies": [{"name": "session", "value": "secret"}],
                                        "postData": {"text": "private"},
                                    }
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            report = runner.redact_har(source, target)
            self.assertFalse(source.exists())
            self.assertTrue(report["raw_deleted"])
            rendered = target.read_text(encoding="utf-8")
            self.assertNotIn("session=secret", rendered)
            self.assertNotIn("Bearer abc", rendered)
            self.assertNotIn("private", rendered)
            self.assertIn("[REDACTED]", rendered)

    def test_finalize_requires_two_unique_contexts_and_stays_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            self._attempt(output, "attempt-01", "ctx-01", "inconsistent", "10:00")
            self._attempt(output, "attempt-02", "ctx-02", "inconsistent", "10:05")
            capture = runner.finalize(
                Namespace(
                    profile=PROFILE,
                    capture_template=TEMPLATE,
                    output_root=output,
                    confirm_screenshots_reviewed=True,
                )
            )
            self.assertEqual(capture["status"], "executed")
            self.assertFalse(capture["payment_submitted"])
            self.assertFalse(capture["reservation_created"])
            self.assertTrue(capture["secrets_redacted"])
            self.assertEqual(len(capture["attempts"]), 2)
            self.assertNotIn("confirmed_defect", capture)
            roles = {item["role"] for item in capture["artifacts"]}
            self.assertEqual(
                roles,
                {
                    "screenshot_before",
                    "screenshot_after",
                    "network_archive",
                    "state_before",
                    "state_after",
                    "transition_trace",
                },
            )

    def test_finalize_rejects_duplicate_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            self._attempt(output, "attempt-01", "ctx-shared", "inconsistent", "10:00")
            self._attempt(output, "attempt-02", "ctx-shared", "inconsistent", "10:05")
            with self.assertRaisesRegex(runner.RunnerError, "context_id values must be unique"):
                runner.finalize(
                    Namespace(
                        profile=PROFILE,
                        capture_template=TEMPLATE,
                        output_root=output,
                        confirm_screenshots_reviewed=True,
                    )
                )

    def _attempt(
        self,
        output: Path,
        attempt_id: str,
        context_id: str,
        result: str,
        minute: str,
    ) -> None:
        directory = output / "attempts" / attempt_id
        directory.mkdir(parents=True)
        checkpoints = {}
        checkpoint_times = {
            "before": f"2026-07-19T{minute}:00+03:00",
            "after_currency": f"2026-07-19T{minute}:10+03:00",
            "after_history": f"2026-07-19T{minute}:20+03:00",
        }
        for name in runner.REQUIRED_CHECKPOINTS:
            state = {
                "checkpoint": name,
                "captured_at": checkpoint_times[name],
                "url": "https://www.airbnb.com/rooms/123",
                "title": "Fixture",
                "display_currency": "TRY" if name == "before" else "EUR",
                "display_total": "18500",
                "visible_money_samples": [],
            }
            state_path = directory / f"{name}.state.json"
            runner.write_json(state_path, state)
            screenshot = directory / f"{name}.png"
            screenshot.write_bytes(f"fixture-{attempt_id}-{name}".encode())
            checkpoints[name] = {
                "state": state,
                "state_path": state_path.name,
                "state_sha256": runner.sha256_file(state_path),
                "screenshot_path": screenshot.name,
                "screenshot_sha256": runner.sha256_file(screenshot),
            }
        network = directory / "network.har"
        runner.write_json(network, {"log": {"entries": []}})
        trace = directory / "transitions.ttrace.jsonl"
        trace.write_text(
            json.dumps(
                {
                    "id": f"{attempt_id}-sense",
                    "type": "sense",
                    "ts": f"2026-07-19T{minute}:00+03:00",
                    "thread_id": runner.RUN_ID,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        attempt = {
            "schema_version": runner.ATTEMPT_SCHEMA,
            "run_id": runner.RUN_ID,
            "profile_id": runner.PROFILE_ID,
            "attempt_id": attempt_id,
            "context_id": context_id,
            "listing_url": "https://www.airbnb.com/rooms/123",
            "started_at": f"2026-07-19T{minute}:00+03:00",
            "completed_at": f"2026-07-19T{minute}:30+03:00",
            "result": result,
            "environment": {
                "browser": "Chromium",
                "browser_version": "fixture",
                "device_timezone": "Europe/Istanbul",
                "locale": "en-US",
                "ip_country": "TR",
                "authenticated": False,
            },
            "safety": {
                "operator_guided": True,
                "automated_clicks": False,
                "payment_submitted": False,
                "reservation_created": False,
                "blocked_request_count": 0,
            },
            "redaction": {
                "har": {"raw_deleted": True},
                "screenshots_reviewed": False,
            },
            "checkpoints": checkpoints,
            "artifacts": {
                "network_archive": {
                    "path": network.name,
                    "sha256": runner.sha256_file(network),
                },
                "transition_trace": {
                    "path": trace.name,
                    "sha256": runner.sha256_file(trace),
                },
            },
        }
        runner.write_json(directory / "attempt.json", attempt)


if __name__ == "__main__":
    unittest.main()
