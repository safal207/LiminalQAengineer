from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path("scripts/hi_rockits_public_audit_probe.py")
SPEC = importlib.util.spec_from_file_location("hi_rockits_probe", MODULE_PATH)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

CONTRACT_PATH = Path("audits/hi-rockits/public-audit-v0.1/contract.json")


class HiRockitsAuditContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_repository_contract_is_valid(self) -> None:
        probe.validate_contract(self.contract)

    def test_occurrence_assertion_requires_minimum_count(self) -> None:
        assertion = {"id": "dup", "type": "occurrence", "marker": "same", "min_occurrences": 2}
        self.assertTrue(probe.evaluate_assertion(assertion, "same / same")["passed"])
        self.assertFalse(probe.evaluate_assertion(assertion, "same once")["passed"])

    def test_all_of_is_case_insensitive(self) -> None:
        assertion = {"id": "all", "type": "all_of", "markers": ["Rockits", "QA"]}
        self.assertTrue(probe.evaluate_assertion(assertion, "ROCKITS qa")["passed"])

    def test_external_submission_must_remain_disabled(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["external_submission_authorized"] = True
        with self.assertRaisesRegex(ValueError, "external_submission_authorized"):
            probe.validate_contract(changed)

    def test_resume_upload_must_remain_disabled(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["resume_upload"] = True
        with self.assertRaisesRegex(ValueError, "resume_upload"):
            probe.validate_contract(changed)

    def test_form_submission_must_remain_disabled(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["form_submission"] = True
        with self.assertRaisesRegex(ValueError, "form_submission"):
            probe.validate_contract(changed)

    def test_outside_origin_target_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://example.com/"
        with self.assertRaisesRegex(ValueError, "outside bounded HTTPS origins"):
            probe.validate_contract(changed)

    def test_query_string_target_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://rockits.ru/?debug=true"
        with self.assertRaisesRegex(ValueError, "query or fragment"):
            probe.validate_contract(changed)


if __name__ == "__main__":
    unittest.main()
