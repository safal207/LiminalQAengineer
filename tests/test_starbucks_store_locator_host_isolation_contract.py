from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "audits/starbucks/store-locator-third-party-isolation-v0.1.json"
SCRIPT = ROOT / "scripts/starbucks_store_locator_host_isolation.mjs"


class StarbucksStoreLocatorHostIsolationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_exact_mobile_store_locator_scope(self):
        self.assertEqual(self.config["target"]["url"], "https://www.starbucks.com/store-locator")
        self.assertEqual(self.config["profile"]["id"], "mobile")
        self.assertTrue(self.config["profile"]["viewport"]["isMobile"])
        self.assertTrue(self.config["profile"]["viewport"]["hasTouch"])

    def test_bounded_inventory_and_isolation(self):
        self.assertEqual(self.config["inventory_rounds"], 3)
        self.assertEqual(self.config["isolation_rounds"], 3)
        self.assertLessEqual(self.config["max_candidate_hosts"], 8)
        self.assertGreaterEqual(self.config["minimum_inventory_presence_rounds"], 2)
        maximum = self.config["inventory_rounds"] + self.config["max_candidate_hosts"] * self.config["isolation_rounds"] * 3
        self.assertLessEqual(maximum, 75)

    def test_data_minimisation_boundaries(self):
        boundaries = self.config["boundaries"]
        for key in (
            "public_page_only",
            "browser_navigation_only",
            "one_active_page_at_a_time",
            "sequential_contexts_only",
            "cache_disabled",
            "service_workers_bypassed",
        ):
            self.assertIs(boundaries[key], True)
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
            "crawling",
            "fuzzing",
            "load_testing",
            "active_security_testing",
            "raw_request_headers_storage",
            "raw_response_headers_storage",
            "raw_request_body_storage",
            "raw_response_body_storage",
            "cookies_storage",
            "web_storage_capture",
            "form_value_storage",
            "console_text_storage",
            "page_error_text_storage",
        ):
            self.assertIs(boundaries[key], False)

    def test_runner_blocks_only_one_exact_script_host(self):
        self.assertIn("r.resourceType() === 'script'", self.script)
        self.assertIn("h === blockedHost", self.script)
        self.assertNotIn("page.authenticate", self.script)
        self.assertNotIn("localStorage", self.script)
        self.assertNotIn("sessionStorage", self.script)
        self.assertNotIn("document.cookie", self.script)

    def test_runner_uses_fresh_context_and_recovery(self):
        self.assertIn("createBrowserContext", self.script)
        self.assertIn("Network.setCacheDisabled", self.script)
        self.assertIn("Network.setBypassServiceWorker", self.script)
        self.assertRegex(self.script, re.compile(r"baseline = await navigate.*treatment = await navigate.*recovery = await navigate", re.S))

    def test_supported_host_dependency_requires_three_of_three(self):
        self.assertEqual(self.config["thresholds"]["supported_failure_rounds"], 3)
        self.assertIn("SUPPORTED_HOST_DEPENDENCY", self.script)
        self.assertIn("cell.treatment_generic_error === c.thresholds.supported_failure_rounds", self.script)
        self.assertIn("cell.recovery_meaningful === required", self.script)

    def test_authority_remains_advisory(self):
        authority = self.config["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for grant in ("ownership", "approval", "execution", "delivery", "external_submission", "deployment", "merge"):
            self.assertIs(authority[grant], False)


if __name__ == "__main__":
    unittest.main()
