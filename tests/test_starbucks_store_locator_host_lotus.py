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


class StarbucksStoreLocatorHostLotusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "standards/lotus-qa/lotus-qa-contract-v0.1.json").read_text(encoding="utf-8")
        )
        cls.findings = json.loads(
            (ROOT / "audits/lotus/starbucks/store-locator-host-isolation-findings-v0.1.json").read_text(encoding="utf-8")
        )
        cls.evidence = json.loads(
            (ROOT / "audits/lotus/starbucks/store-locator-host-isolation-evidence-v0.1.json").read_text(encoding="utf-8")
        )
        cls.packet = module.build_packet(cls.contract, cls.findings)
        cls.by_id = {item["finding_id"]: item for item in cls.packet["findings"]}

    def test_exact_source_pin(self):
        source = self.evidence["source"]
        self.assertEqual(source["workflow"], "Starbucks Store Locator Third-Party Host Isolation")
        self.assertEqual(source["run_id"], 29676480938)
        self.assertEqual(source["exact_head_sha"], "33608dcdc0f9854afab19a111469fd870e8037bd")
        self.assertEqual(source["artifact_id"], 8439113486)
        self.assertEqual(
            source["artifact_digest"],
            "sha256:8168beee4862a4514c9411954a4200e668eec7a46009a047b6e70760e6c0005e",
        )
        self.assertEqual(source["result_sha256"], "527c7e3bc98c50f88027846eb726df38f91f990c9956d717f9f72ed7663a1b61")

    def test_maps_dependency_exact_three_round_contract(self):
        result = self.evidence["maps_googleapis_result"]
        self.assertEqual(result["verdict"], "SUPPORTED_HOST_DEPENDENCY")
        self.assertEqual(result["baseline_meaningful_rounds"], 3)
        self.assertEqual(result["treatment_blocked_rounds"], 3)
        self.assertEqual(result["blocked_script_requests_per_round"], 1)
        self.assertEqual(result["generic_error_rounds"], 3)
        self.assertEqual(result["route_identity_lost_rounds"], 3)
        self.assertEqual(result["visible_inputs_in_treatment"], [0, 0, 0])
        self.assertEqual(result["recovery_meaningful_rounds"], 3)
        self.assertEqual(result["baseline_text_sha256"], result["recovery_text_sha256"])
        self.assertEqual(result["baseline_screenshot_sha256"], result["recovery_screenshot_sha256"])

    def test_seven_hosts_are_negative_controls(self):
        controls = self.evidence["neutral_controls"]
        self.assertEqual(len(controls), 7)
        for control in controls:
            self.assertEqual(control["blocked_rounds"], 3)
            self.assertEqual(control["meaningful_treatment_rounds"], 3)
            self.assertEqual(control["generic_error_rounds"], 0)
            self.assertEqual(control["recovery_rounds"], 3)

    def test_ninth_stable_host_is_not_silently_classified(self):
        host = self.evidence["inventory"]["stable_hosts_seen"]["resources.xg4ken.com"]
        self.assertEqual(host["presence_rounds"], 3)
        self.assertEqual(host["script_requests"], 3)
        self.assertIs(host["isolated"], False)

    def test_three_way_lotus_result(self):
        self.assertEqual(self.packet["summary"]["finding_count"], 3)
        self.assertEqual(
            self.packet["summary"]["pythia_verdicts"],
            {"ALLOW": 1, "BLOCK": 1, "ESCALATE": 1},
        )
        self.assertEqual(
            self.packet["summary"]["decision_statuses"],
            {"BLOCKED": 1, "CONFIRMED": 1, "NEEDS_EVIDENCE": 1},
        )
        self.assertEqual(
            self.packet["summary"]["user_control_risks"],
            {"MEDIUM": 1, "NONE": 1, "UNKNOWN": 1},
        )

    def test_maps_dependency_is_confirmed_p2_not_provider_fault(self):
        finding = self.by_id["SBX-STORE-MAPS-SCRIPT-DEPENDENCY-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ALLOW")
        self.assertEqual(finding["decision"]["status"], "CONFIRMED")
        self.assertEqual(finding["decision"]["severity"], "P2")
        self.assertEqual(finding["user_control"]["risk"], "MEDIUM")
        self.assertEqual(finding["causal_memory"]["status"], "PROPOSED_RECURRING")
        self.assertNotIn("provider fault", finding["claim"].lower())

    def test_broad_all_hosts_claim_is_negative_memory(self):
        finding = self.by_id["SBX-STORE-ANY-THIRD-PARTY-CRASH-HYPOTHESIS-001"]
        self.assertEqual(finding["judgment"]["verdict"], "BLOCK")
        self.assertEqual(finding["decision"]["status"], "BLOCKED")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["causal_memory"]["status"], "NEGATIVE_CAUSAL_MEMORY")

    def test_untested_host_has_no_severity(self):
        finding = self.by_id["SBX-STORE-XG4KEN-UNTESTED-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ESCALATE")
        self.assertEqual(finding["decision"]["status"], "NEEDS_EVIDENCE")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["user_control"]["risk"], "UNKNOWN")

    def test_no_durable_or_execution_authority(self):
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
