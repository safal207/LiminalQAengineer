from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "audits/starbucks/route-resilience-matrix-v0.1.json"
SCRIPT_PATH = ROOT / "scripts/starbucks_route_resilience_matrix.mjs"


class StarbucksRouteResilienceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_exact_public_route_matrix(self):
        self.assertEqual(
            [target["url"] for target in self.config["targets"]],
            [
                "https://www.starbucks.com/menu",
                "https://www.starbucks.com/store-locator",
                "https://www.starbucks.com/account/signin",
                "https://www.starbucks.com/rewards",
                "https://www.starbucks.com/gift",
            ],
        )
        self.assertEqual([profile["id"] for profile in self.config["profiles"]], ["desktop", "mobile"])
        self.assertEqual(self.config["rounds"], 3)

    def test_navigation_budget_is_exact_and_sequential(self):
        planned = len(self.config["targets"]) * len(self.config["profiles"]) * self.config["rounds"] * 4
        self.assertEqual(planned, 120)
        boundaries = self.config["boundaries"]
        self.assertEqual(boundaries["maximum_total_navigations"], planned)
        self.assertEqual(boundaries["maximum_parallel_pages"], 1)
        self.assertIs(boundaries["sequential_contexts_only"], True)

    def test_no_authenticated_or_mutating_activity_is_allowed(self):
        boundaries = self.config["boundaries"]
        self.assertIs(boundaries["public_pages_only"], True)
        self.assertIs(boundaries["natural_browser_requests_only"], True)
        for key in (
            "authentication",
            "account_creation",
            "form_submission",
            "orders_or_payments",
            "gift_card_balance_check",
            "rewards_mutation",
            "direct_application_api_calls",
            "credential_validation",
            "token_requests",
            "fuzzing",
            "load_testing",
            "active_security_testing",
        ):
            self.assertIs(boundaries[key], False, key)

    def test_artifact_minimization_is_explicit(self):
        boundaries = self.config["boundaries"]
        for key in (
            "raw_response_body_storage",
            "request_header_storage",
            "cookie_storage",
            "local_storage_capture",
            "form_value_capture",
        ):
            self.assertIs(boundaries[key], False, key)

    def test_treatment_and_recovery_contract_is_present(self):
        for phase in (
            "baseline",
            "third_party_scripts_blocked",
            "first_party_scripts_blocked",
            "recovery",
        ):
            self.assertIn(phase, self.script)
        self.assertIn("Network.setCacheDisabled", self.script)
        self.assertIn("setBypassServiceWorker", self.script)
        self.assertIn("Accessibility.getFullAXTree", self.script)
        self.assertIn("first-party-isolation-confounded", self.script)

    def test_authority_boundary_is_non_executive(self):
        authority = self.config["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for grant in (
            "ownership",
            "approval",
            "execution",
            "delivery",
            "external_submission",
            "deployment",
            "merge",
        ):
            self.assertIs(authority[grant], False, grant)


if __name__ == "__main__":
    unittest.main()
