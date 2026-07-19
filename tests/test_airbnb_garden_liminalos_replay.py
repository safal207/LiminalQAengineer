from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "audits/airbnb/airbnb-garden-liminalos-replay-v0.1.json"
SCRIPT_PATH = ROOT / "scripts/airbnb_garden_liminalos_replay.py"

spec = importlib.util.spec_from_file_location("airbnb_garden_replay", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class AirbnbGardenLiminalOSReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_exact_source_and_runtime_pins(self) -> None:
        source = self.config["source_evidence"]
        self.assertEqual(source["execution_pr"], 77)
        self.assertEqual(source["adjudication_pr"], 80)
        self.assertEqual(source["execution_head"], "404da0d714de334e18080138623370fdc32717f5")
        self.assertEqual(source["workflow_run_id"], 29678020284)
        self.assertEqual(source["artifact_id"], 8439609413)
        self.assertEqual(
            source["artifact_digest"],
            "sha256:55030ae08db9d7f462aec48a75ce11873deb32d4f44255ffc01c3b7b1e06ad49",
        )
        self.assertEqual(
            self.config["garden"]["commit"],
            "6c30422d0492ec312a35624322f90a7761419655",
        )
        self.assertEqual(
            self.config["liminalos"]["commit"],
            "a2c5783287a9def4b4254b9436c2e75468613dca",
        )

    def test_same_evidence_and_non_retroactive_boundary(self) -> None:
        contract = self.config["comparison_contract"]
        self.assertIs(contract["same_evidence_replay"], True)
        self.assertIs(contract["live_airbnb_navigation"], False)
        self.assertIs(contract["retroactive_garden_isolation_claim_allowed"], False)
        self.assertIs(contract["liminalos_output_is_advisory_only"], True)
        self.assertIs(contract["aborted_requests_without_user_impact_are_not_product_defects"], True)

    def test_liminalos_has_no_defect_or_execution_authority(self) -> None:
        liminalos = self.config["liminalos"]
        self.assertIs(liminalos["may_confirm_product_defect"], False)
        self.assertIs(liminalos["may_grant_execution_authority"], False)

    def test_attempt_inspection_detects_exact_identity_and_currency_sequence(self) -> None:
        attempt = {
            "attempt_id": "attempt-01",
            "outcome": "consistent",
            "states": [
                {
                    "requested_currency": currency,
                    "inferred_visible_currency": currency,
                    "final_url": f"https://www.airbnb.com/rooms/1418689551881927394?currency={currency}",
                }
                for currency in ("TRY", "EUR", "TRY", "EUR")
            ],
            "runtime_errors": [],
            "console_error_count": 0,
            "page_errors": [],
            "request_failures": [
                {"url": "https://www.airbnb.com/tracking", "error": "net::ERR_ABORTED"}
            ],
            "http_4xx_5xx": [],
            "payment_submitted": False,
            "reservation_created": False,
        }
        result = module.inspect_attempt(attempt, "1418689551881927394")
        self.assertTrue(result["expected_sequence_match"])
        self.assertTrue(result["target_identity_stable"])
        self.assertTrue(result["url_and_visible_currency_aligned"])
        self.assertEqual(result["request_failure_count"], 1)
        self.assertEqual(result["request_failure_reasons"], {"net::ERR_ABORTED": 1})

    def test_attempt_inspection_rejects_target_drift(self) -> None:
        attempt = {
            "attempt_id": "attempt-drift",
            "outcome": "consistent",
            "states": [
                {
                    "requested_currency": currency,
                    "inferred_visible_currency": currency,
                    "final_url": f"https://www.airbnb.com/rooms/999?currency={currency}",
                }
                for currency in ("TRY", "EUR", "TRY", "EUR")
            ],
        }
        result = module.inspect_attempt(attempt, "1418689551881927394")
        self.assertFalse(result["target_identity_stable"])

    def test_manifest_verification_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "payload.txt"
            payload.write_text("original", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps([{"path": "payload.txt", "sha256": module.sha256(payload)}]),
                encoding="utf-8",
            )
            self.assertTrue(module.verify_manifest(root, manifest)["valid"])
            payload.write_text("changed", encoding="utf-8")
            self.assertFalse(module.verify_manifest(root, manifest)["valid"])

    def test_script_contains_no_live_airbnb_client(self) -> None:
        self.assertNotIn("playwright", self.script.lower())
        self.assertNotIn("requests.get", self.script)
        self.assertNotIn("urllib.request", self.script)
        self.assertIn("same exact Airbnb artifact", self.script)

    def test_authority_is_fully_false(self) -> None:
        authority = self.config["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for key in (
            "ownership",
            "approval",
            "execution",
            "delivery",
            "external_submission",
            "deployment",
            "merge",
        ):
            self.assertIs(authority[key], False)


if __name__ == "__main__":
    unittest.main()
