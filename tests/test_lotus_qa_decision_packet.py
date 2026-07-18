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


class LotusQADecisionPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "standards/lotus-qa/lotus-qa-contract-v0.1.json").read_text())
        cls.findings = json.loads((ROOT / "audits/lotus/lotus-findings-v0.1.json").read_text())
        cls.packet = module.build_packet(cls.contract, cls.findings)

    def test_contract_pins_all_three_lotus_projects(self):
        sources = self.packet["contract"]["source_contracts"]
        self.assertEqual(set(sources), {"pythia", "cml", "ls"})
        self.assertEqual(sources["pythia"]["commit"], "03efe66e1d7920480fe6fa1dc310fe6b17faaf80")
        self.assertEqual(sources["cml"]["commit"], "33f904d28c78a560aaab3b0be4f6fd501f22116d")
        self.assertEqual(sources["ls"]["commit"], "c9b070682a6a405553fa29f18bc95dc9e5d9c232")

    def test_authority_is_audit_only_and_all_grants_are_false(self):
        authority = self.packet["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for key in ("ownership", "approval", "execution", "delivery", "deployment", "merge"):
            self.assertIs(authority[key], False)
        for finding in self.packet["findings"]:
            self.assertEqual(finding["authority"], authority)

    def test_expected_three_way_judgment_is_preserved(self):
        self.assertEqual(self.packet["summary"]["pythia_verdicts"], {"ALLOW": 5, "BLOCK": 1, "ESCALATE": 1})
        self.assertEqual(self.packet["summary"]["decision_statuses"], {"BLOCKED": 1, "CONFIRMED": 5, "NEEDS_EVIDENCE": 1})
        by_id = {item["finding_id"]: item for item in self.packet["findings"]}
        self.assertEqual(by_id["TRADERNET-HERO-DISCOVERY-001"]["judgment"]["verdict"], "ALLOW")
        self.assertEqual(by_id["TRADERNET-REDIRECT-DOMINANT-001"]["judgment"]["verdict"], "BLOCK")
        self.assertEqual(by_id["OPENAI-HOMEPAGE-W750-CAUSE-001"]["judgment"]["verdict"], "ESCALATE")

    def test_cml_never_silently_accepts_memory(self):
        self.assertEqual(self.packet["summary"]["durable_memory_count"], 0)
        for finding in self.packet["findings"]:
            self.assertFalse(finding["causal_memory"]["durable_memory"])
        by_id = {item["finding_id"]: item for item in self.packet["findings"]}
        self.assertEqual(by_id["OPENAI-HOMEPAGE-W750-CAUSE-001"]["causal_memory"]["status"], "CONFLICT")
        self.assertEqual(by_id["TRADERNET-REDIRECT-DOMINANT-001"]["causal_memory"]["status"], "NEGATIVE_CAUSAL_MEMORY")

    def test_ls_keeps_unknown_user_impact_explicit(self):
        by_id = {item["finding_id"]: item for item in self.packet["findings"]}
        self.assertEqual(by_id["TAKEPROFIT-CHARTSTORE-REGRESSION-001"]["user_control"]["risk"], "UNKNOWN")
        self.assertEqual(by_id["OPENAI-HOMEPAGE-W750-CAUSE-001"]["user_control"]["risk"], "UNKNOWN")
        self.assertEqual(by_id["OPENAI-STATUS-ACCESSIBILITY-001"]["user_control"]["risk"], "MEDIUM")

    def test_only_confirmed_findings_receive_severity(self):
        for finding in self.packet["findings"]:
            if finding["decision"]["status"] == "CONFIRMED":
                self.assertEqual(finding["decision"]["severity"], finding["decision"]["severity_candidate"])
            else:
                self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")

    def test_packet_is_deterministic(self):
        second = module.build_packet(self.contract, self.findings)
        self.assertEqual(self.packet, second)
        self.assertEqual(self.packet["packet_sha256"], "7c77d1ac2ee5872936ac4c90b48a28b3d8c2fd713ab7cf53ab8606feb2d3d7ff")


if __name__ == "__main__":
    unittest.main()
