from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path("scripts/bell_integrator_public_audit_probe.py")
SPEC = importlib.util.spec_from_file_location("bell_integrator_probe", MODULE_PATH)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)

CONTRACT_PATH = Path("audits/bell-integrator/public-audit-v0.1/contract.json")


class BellIntegratorAuditContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_repository_contract_is_valid(self) -> None:
        probe.validate_contract(self.contract)

    def test_occurrence_assertion_requires_minimum_count(self) -> None:
        assertion = {
            "id": "duplicate",
            "type": "occurrence",
            "marker": "same copy",
            "min_occurrences": 2,
        }
        self.assertTrue(probe.evaluate_assertion(assertion, "same copy / same copy")["passed"])
        self.assertFalse(probe.evaluate_assertion(assertion, "same copy only once")["passed"])

    def test_all_of_is_case_insensitive_by_default(self) -> None:
        assertion = {
            "id": "all",
            "type": "all_of",
            "markers": ["Bell Integrator", "QA"],
        }
        result = probe.evaluate_assertion(assertion, "BELL INTEGRATOR provides qa services")
        self.assertTrue(result["passed"])

    def test_external_submission_must_remain_disabled(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["external_submission_authorized"] = True
        with self.assertRaisesRegex(ValueError, "external_submission_authorized"):
            probe.validate_contract(changed)

    def test_form_submission_must_remain_disabled(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["form_submission"] = True
        with self.assertRaisesRegex(ValueError, "form_submission"):
            probe.validate_contract(changed)

    def test_outside_origin_target_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://example.com/"
        with self.assertRaisesRegex(ValueError, "outside bounded HTTPS origin"):
            probe.validate_contract(changed)

    def test_query_string_target_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://bellintegrator.ru/?debug=true"
        with self.assertRaisesRegex(ValueError, "query or fragment"):
            probe.validate_contract(changed)


if __name__ == "__main__":
    unittest.main()
