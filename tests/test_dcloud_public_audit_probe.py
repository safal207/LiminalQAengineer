from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.dcloud_public_audit_probe import evaluate_assertion, validate_contract


CONTRACT_PATH = Path("audits/dcloud/public-audit-v0.1/contract.json")


class DCloudPublicAuditProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_repository_contract_is_valid(self) -> None:
        validate_contract(self.contract)

    def test_all_of_requires_every_marker(self) -> None:
        assertion = {
            "id": "contact_identity",
            "type": "all_of",
            "markers": ["hr@dcloud.tech", "© 2025 DCloud"],
        }
        result = evaluate_assertion(assertion, "Contact hr@dcloud.tech · © 2025 DCloud")
        self.assertTrue(result["passed"])

        incomplete = evaluate_assertion(assertion, "Contact hr@dcloud.tech")
        self.assertFalse(incomplete["passed"])

    def test_occurrence_assertion_preserves_duplication_signal(self) -> None:
        assertion = {
            "id": "duplicate_role_copy",
            "type": "occurrence",
            "marker": "Backend/Fullstack Developer",
            "min_occurrences": 4,
        }
        text = " · ".join(["Backend/Fullstack Developer"] * 4)
        result = evaluate_assertion(assertion, text)
        self.assertTrue(result["passed"])
        self.assertEqual(result["observed_occurrences"], 4)

    def test_contract_fails_closed_if_external_reporting_is_enabled(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["external_submission_authorized"] = True
        with self.assertRaisesRegex(ValueError, "external_submission_authorized must be false"):
            validate_contract(changed)

    def test_contract_rejects_target_outside_allowlist(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://example.com/"
        with self.assertRaisesRegex(ValueError, "outside the bounded HTTPS origin"):
            validate_contract(changed)


if __name__ == "__main__":
    unittest.main()
