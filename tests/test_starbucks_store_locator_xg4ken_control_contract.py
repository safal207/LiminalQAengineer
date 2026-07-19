from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "audits/starbucks/store-locator-xg4ken-control-v0.1.json"
SCRIPT = ROOT / "scripts/starbucks_store_locator_xg4ken_control.mjs"


class StarbucksStoreLocatorXg4kenControlContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_exact_mobile_scope_and_host(self):
        self.assertEqual(self.config["target"]["url"], "https://www.starbucks.com/store-locator")
        self.assertEqual(self.config["blocked_host"], "resources.xg4ken.com")
        self.assertEqual(self.config["profile"]["id"], "mobile")
        self.assertTrue(self.config["profile"]["viewport"]["isMobile"])
        self.assertTrue(self.config["profile"]["viewport"]["hasTouch"])

    def test_three_rounds_and_nine_navigations(self):
        self.assertEqual(self.config["rounds"], 3)
        self.assertEqual(self.config["thresholds"]["required_rounds"], 3)
        self.assertEqual(self.config["boundaries"]["maximum_navigations"], 9)

    def test_runner_blocks_only_exact_script_host(self):
        self.assertIn("request.resourceType() === 'script'", self.script)
        self.assertIn("host === config.blocked_host", self.script)
        self.assertIn("blocked_target_host_script_requests", self.script)
        self.assertNotIn("page.authenticate", self.script)
        self.assertNotIn("document.cookie", self.script)
        self.assertNotIn("localStorage", self.script)
        self.assertNotIn("sessionStorage", self.script)

    def test_route_identity_excludes_url_path(self):
        self.assertIn("const identityHaystack = `${document.title || ''} ${text}`", self.script)
        self.assertNotIn("location.pathname} ${document.title", self.script)

    def test_fresh_context_baseline_treatment_recovery(self):
        self.assertIn("createBrowserContext", self.script)
        self.assertIn("Network.setCacheDisabled", self.script)
        self.assertIn("Network.setBypassServiceWorker", self.script)
        self.assertRegex(
            self.script,
            re.compile(
                r"baseline = await capture.*treatment = await capture.*recovery = await capture",
                re.S,
            ),
        )

    def test_classification_requires_host_presence_block_and_recovery(self):
        self.assertIn("result.baseline_host_observed === required", self.script)
        self.assertIn("result.treatment_host_blocked === required", self.script)
        self.assertIn("result.recovery_meaningful === required", self.script)
        self.assertIn("SUPPORTED_HOST_DEPENDENCY", self.script)
        self.assertIn("NEUTRAL_UNDER_BOUNDED_TEST", self.script)

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

    def test_authority_remains_audit_only(self):
        authority = self.config["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for grant in ("ownership", "approval", "execution", "delivery", "external_submission", "deployment", "merge"):
            self.assertIs(authority[grant], False)


if __name__ == "__main__":
    unittest.main()
