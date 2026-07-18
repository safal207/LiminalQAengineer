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


class RevolutLotusPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "standards/lotus-qa/lotus-qa-contract-v0.1.json").read_text(encoding="utf-8")
        )
        cls.findings = json.loads(
            (ROOT / "audits/lotus/revolut/revolut-findings-v0.1.json").read_text(encoding="utf-8")
        )
        cls.evidence = json.loads(
            (ROOT / "audits/lotus/revolut/revolut-public-evidence-v0.1.json").read_text(encoding="utf-8")
        )
        cls.packet = module.build_packet(cls.contract, cls.findings)
        cls.by_id = {item["finding_id"]: item for item in cls.packet["findings"]}

    def test_scope_is_public_read_only(self):
        scope = self.evidence["scope"]
        self.assertEqual(scope["mode"], "public_read_only")
        for key in (
            "authentication",
            "financial_operations",
            "direct_application_api_calls",
            "load_testing",
            "exploitation",
        ):
            self.assertIs(scope[key], False)

    def test_current_official_revolut_x_commit_is_pinned(self):
        source = self.evidence["official_sources"]["revolut_x_repository"]
        self.assertEqual(source["commit"], "13778de69e0411ee11198dc913a3b9b0f72ac880")
        self.assertEqual(
            source["files"]["api/src/http/request.ts"],
            "6afcdcac728ff2fc9f347ce5e2a90a0cf8cf4495",
        )
        self.assertEqual(
            source["files"]["revolut-x-api-for-llm.md"],
            "db0a43aa4ce82ec496f29aa16ecfc20145dd0672",
        )

    def test_expected_three_way_lotus_decision(self):
        self.assertEqual(self.packet["summary"]["finding_count"], 9)
        self.assertEqual(
            self.packet["summary"]["pythia_verdicts"],
            {"ALLOW": 7, "BLOCK": 1, "ESCALATE": 1},
        )
        self.assertEqual(
            self.packet["summary"]["decision_statuses"],
            {"BLOCKED": 1, "CONFIRMED": 7, "NEEDS_EVIDENCE": 1},
        )
        self.assertEqual(
            self.packet["summary"]["user_control_risks"],
            {"HIGH": 1, "LOW": 1, "MEDIUM": 5, "NONE": 1, "UNKNOWN": 1},
        )

    def test_retry_after_is_confirmed_and_high_user_control_risk(self):
        finding = self.by_id["RVLT-X-RETRY-AFTER-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ALLOW")
        self.assertEqual(finding["decision"]["status"], "CONFIRMED")
        self.assertEqual(finding["decision"]["severity"], "P2")
        self.assertEqual(finding["user_control"]["risk"], "HIGH")
        self.assertEqual(finding["causal_memory"]["status"], "PROPOSED_RECURRING")

    def test_deep_link_candidate_cannot_receive_severity(self):
        finding = self.by_id["RVLT-WEB-DEEPLINK-INTERMITTENT-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ESCALATE")
        self.assertEqual(finding["decision"]["status"], "NEEDS_EVIDENCE")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["causal_memory"]["status"], "CONFLICT")

    def test_descending_asks_claim_is_negative_memory(self):
        finding = self.by_id["RVLT-X-ASKS-DESCENDING-HYPOTHESIS-001"]
        self.assertEqual(finding["judgment"]["verdict"], "BLOCK")
        self.assertEqual(finding["decision"]["status"], "BLOCKED")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["causal_memory"]["status"], "NEGATIVE_CAUSAL_MEMORY")

    def test_no_memory_or_execution_authority_is_granted(self):
        self.assertEqual(self.packet["summary"]["durable_memory_count"], 0)
        authority = self.packet["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for grant in ("ownership", "approval", "execution", "delivery", "deployment", "merge"):
            self.assertIs(authority[grant], False)
        for finding in self.packet["findings"]:
            self.assertFalse(finding["causal_memory"]["durable_memory"])
            self.assertEqual(finding["authority"], authority)

    def test_packet_is_deterministic(self):
        second = module.build_packet(self.contract, self.findings)
        self.assertEqual(self.packet, second)
        self.assertEqual(len(self.packet["packet_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
