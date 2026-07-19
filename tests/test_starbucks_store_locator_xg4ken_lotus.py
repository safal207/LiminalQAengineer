from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lotus_qa_decision_packet.py"
spec = importlib.util.spec_from_file_location("lotus_qa_decision_packet", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class StarbucksStoreLocatorXg4kenLotusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "standards/lotus-qa/lotus-qa-contract-v0.1.json").read_text(encoding="utf-8"))
        cls.findings = json.loads((ROOT / "audits/lotus/starbucks/store-locator-xg4ken-findings-v0.1.json").read_text(encoding="utf-8"))
        cls.evidence = json.loads((ROOT / "audits/lotus/starbucks/store-locator-xg4ken-evidence-v0.1.json").read_text(encoding="utf-8"))
        cls.packet = module.build_packet(cls.contract, cls.findings)
        cls.by_id = {item["finding_id"]: item for item in cls.packet["findings"]}

    def test_two_way_decision(self):
        self.assertEqual(self.packet["summary"]["finding_count"], 2)
        self.assertEqual(self.packet["summary"]["pythia_verdicts"], {"ALLOW": 1, "BLOCK": 1})
        self.assertEqual(self.packet["summary"]["decision_statuses"], {"BLOCKED": 1, "CONFIRMED": 1})
        self.assertEqual(self.packet["summary"]["user_control_risks"], {"NONE": 2})

    def test_neutral_control_is_confirmed(self):
        finding = self.by_id["SBX-STORE-XG4KEN-NEUTRAL-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ALLOW")
        self.assertEqual(finding["decision"]["status"], "CONFIRMED")
        self.assertEqual(finding["decision"]["severity"], "P3")
        self.assertEqual(finding["causal_memory"]["status"], "PROPOSED_RECURRING")
        self.assertEqual(finding["user_control"]["risk"], "NONE")
        self.assertEqual(finding["evidence"]["supersedes_finding_id"], "SBX-STORE-XG4KEN-UNTESTED-001")

    def test_crash_hypothesis_is_negative_memory(self):
        finding = self.by_id["SBX-STORE-XG4KEN-CRASH-HYPOTHESIS-001"]
        self.assertEqual(finding["judgment"]["verdict"], "BLOCK")
        self.assertEqual(finding["decision"]["status"], "BLOCKED")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["causal_memory"]["status"], "NEGATIVE_CAUSAL_MEMORY")
        self.assertEqual(finding["user_control"]["risk"], "NONE")

    def test_exact_evidence_closes_previous_gap(self):
        self.assertEqual(self.evidence["classification"]["verdict"], "NEUTRAL_UNDER_BOUNDED_TEST")
        self.assertEqual(self.evidence["classification"]["baseline_host_observed"], 3)
        self.assertEqual(self.evidence["classification"]["treatment_host_blocked"], 3)
        self.assertEqual(self.evidence["classification"]["treatment_generic_error"], 0)
        self.assertEqual(self.evidence["classification"]["treatment_meaningful"], 3)
        self.assertEqual(self.evidence["classification"]["recovery_meaningful"], 3)
        self.assertTrue(self.evidence["stable_visible_state"]["identical_across_baseline_treatment_recovery"])
        self.assertTrue(self.evidence["stable_visible_state"]["identical_across_all_three_rounds"])
        self.assertEqual(self.evidence["supersession"]["prior_state"], "NEEDS_EVIDENCE")
        self.assertEqual(self.evidence["supersession"]["new_state"], "CONFIRMED_NEUTRAL_CONTROL")

    def test_authority_remains_advisory(self):
        self.assertEqual(self.packet["summary"]["durable_memory_count"], 0)
        authority = self.packet["authority"]
        for grant in ("ownership", "approval", "execution", "delivery", "deployment", "merge"):
            self.assertIs(authority[grant], False)
        for finding in self.packet["findings"]:
            self.assertFalse(finding["causal_memory"]["durable_memory"])

    def test_packet_is_deterministic(self):
        second = module.build_packet(self.contract, self.findings)
        self.assertEqual(self.packet, second)
        self.assertEqual(len(self.packet["packet_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
