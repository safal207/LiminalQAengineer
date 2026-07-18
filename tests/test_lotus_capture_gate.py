import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/lotus_capture_gate.py"
SPEC = importlib.util.spec_from_file_location("lotus_capture_gate", MODULE_PATH)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

SPEC_PATH = ROOT / "integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json"
TEMPLATE_PATH = ROOT / "integrations/lotus/examples/airbnb-run-002.capture.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LotusCaptureGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        self.template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_planned_template_stays_f0_and_unconfirmed(self) -> None:
        result = gate.validate_capture(self.spec, self.template, TEMPLATE_PATH.parent)
        self.assertEqual(result.status, "PLANNED")
        self.assertEqual(result.evidence_grade, "F0")
        self.assertFalse(result.ready_for_review)
        self.assertFalse(result.confirmed_defect)

    def test_payment_submission_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.template)
        invalid["payment_submitted"] = True
        with self.assertRaisesRegex(gate.CaptureError, "payment_submitted"):
            gate.validate_capture(self.spec, invalid, TEMPLATE_PATH.parent)

    def test_executed_capture_requires_two_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"] = capture["attempts"][:1]
            with self.assertRaisesRegex(gate.CaptureError, "two independent attempts"):
                gate.validate_capture(self.spec, capture, root)

    def test_complete_repeated_capture_is_ready_but_not_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            result = gate.validate_capture(self.spec, capture, root)
            self.assertEqual(result.status, "READY_FOR_REVIEW")
            self.assertEqual(result.evidence_grade, "F3")
            self.assertTrue(result.ready_for_review)
            self.assertFalse(result.confirmed_defect)

    def test_sha_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["artifacts"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(gate.CaptureError, "SHA mismatch"):
                gate.validate_capture(self.spec, capture, root)

    def _executed_capture(self, root: Path) -> dict:
        roles = sorted(gate.REQUIRED_ARTIFACT_ROLES)
        artifacts = []
        for role in roles:
            path = root / f"{role}.txt"
            path.write_text(f"redacted evidence for {role}\n", encoding="utf-8")
            artifacts.append({"role": role, "path": path.name, "sha256": digest(path)})

        state_before = {
            "display_currency": "TRY",
            "display_total": "18500",
            "captured_at": "2026-07-19T10:00:00+03:00",
        }
        state_after = {
            "display_currency": "EUR",
            "display_total": "18500",
            "captured_at": "2026-07-19T10:00:05+03:00",
        }
        attempts = [
            {
                "attempt_id": "attempt-1",
                "result": "inconsistent",
                "state_before": state_before,
                "state_after": state_after,
            },
            {
                "attempt_id": "attempt-2",
                "result": "inconsistent",
                "state_before": {
                    **state_before,
                    "captured_at": "2026-07-19T10:05:00+03:00",
                },
                "state_after": {
                    **state_after,
                    "captured_at": "2026-07-19T10:05:05+03:00",
                },
            },
        ]
        return {
            "capture_version": "lqa-lotus-browser-capture/0.1",
            "run_id": "ABNB-RUN-002",
            "target": "Airbnb",
            "profile_id": "airbnb-currency-atomicity-v0.1",
            "status": "executed",
            "payment_submitted": False,
            "reservation_created": False,
            "secrets_redacted": True,
            "started_at": "2026-07-19T10:00:00+03:00",
            "completed_at": "2026-07-19T10:06:00+03:00",
            "environment": {
                "browser": "Chromium",
                "browser_version": "fixture",
                "device_timezone": "Europe/Istanbul",
                "locale": "en-US",
                "ip_country": "TR",
                "authenticated": False,
            },
            "attempts": attempts,
            "artifacts": artifacts,
        }


if __name__ == "__main__":
    unittest.main()
