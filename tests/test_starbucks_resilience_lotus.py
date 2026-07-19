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


class StarbucksResilienceLotusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "standards/lotus-qa/lotus-qa-contract-v0.1.json").read_text(encoding="utf-8")
        )
        cls.findings = json.loads(
            (ROOT / "audits/lotus/starbucks/starbucks-resilience-findings-v0.1.json").read_text(encoding="utf-8")
        )
        cls.evidence = json.loads(
            (ROOT / "audits/starbucks/route-resilience-result-v0.1.json").read_text(encoding="utf-8")
        )
        cls.packet = module.build_packet(cls.contract, cls.findings)
        cls.by_id = {item["finding_id"]: item for item in cls.packet["findings"]}

    def test_exact_run_and_artifact_are_pinned(self):
        observation = self.evidence["observation"]
        self.assertEqual(observation["head_sha"], "1f7d330df7018ed28ee500a04ff7dcbaa0b21c28")
        self.assertEqual(observation["workflow_run_id"], 29667373889)
        self.assertEqual(observation["artifact_id"], 8436241393)
        self.assertEqual(
            observation["artifact_digest"],
            "sha256:4fd8eb493d0a20b66d5d0f3a794ed597bf92c7a831366edf987dfa3470376a88",
        )
        self.assertEqual(observation["aggregate_file_sha256"], "cd2dde59145998b5c555ffbe07f73031e9d5e8d978bc116212f644d54cc7470a")

    def test_matrix_result_is_complete(self):
        matrix = self.evidence["matrix"]
        self.assertEqual(matrix["fresh_browser_contexts"], 30)
        self.assertEqual(matrix["navigations"], 120)
        self.assertEqual(matrix["cells"], 10)
        self.assertEqual(matrix["supported_cells"], 9)
        self.assertEqual(matrix["needs_evidence_cells"], 1)

    def test_first_party_treatment_is_silent_and_recoverable(self):
        treatment = self.evidence["first_party_javascript_treatment"]
        self.assertEqual(treatment["pairs"], 30)
        self.assertEqual(treatment["pairs_with_first_party_script_block"], 30)
        self.assertEqual(treatment["pairs_without_main_landmark"], 30)
        self.assertEqual(treatment["pairs_without_route_identity"], 30)
        self.assertEqual(treatment["pairs_with_javascript_required_message"], 0)
        self.assertEqual(treatment["pairs_with_recovery_guidance"], 0)
        self.assertEqual(treatment["pairs_recovered_after_scripts_restored"], 30)

    def test_mobile_store_locator_third_party_error_is_repeated(self):
        treatment = self.evidence["mobile_store_locator_third_party_treatment"]
        self.assertEqual(treatment["rounds"], 3)
        self.assertEqual(treatment["generic_error_screen_rounds"], 3)
        self.assertEqual(treatment["route_identity_rounds"], 0)
        self.assertEqual(treatment["recovery_guidance_rounds"], 3)
        self.assertEqual(treatment["recovery_restored_rounds"], 3)
        self.assertEqual(treatment["desktop_third_party_control_valid_rounds"], 3)

    def test_two_findings_are_confirmed(self):
        self.assertEqual(self.packet["summary"]["finding_count"], 2)
        self.assertEqual(self.packet["summary"]["pythia_verdicts"], {"ALLOW": 2})
        self.assertEqual(self.packet["summary"]["decision_statuses"], {"CONFIRMED": 2})
        self.assertEqual(self.packet["summary"]["user_control_risks"], {"MEDIUM": 2})
        self.assertEqual(self.packet["summary"]["durable_memory_count"], 0)

    def test_silent_shell_finding_is_confirmed(self):
        finding = self.by_id["SBX-WEB-FIRST-PARTY-JS-SILENT-SHELL-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ALLOW")
        self.assertEqual(finding["decision"]["status"], "CONFIRMED")
        self.assertEqual(finding["decision"]["severity"], "P2")
        self.assertEqual(finding["user_control"]["risk"], "MEDIUM")
        self.assertEqual(finding["causal_memory"]["status"], "PROPOSED_RECURRING")

    def test_mobile_store_locator_finding_is_confirmed_without_provider_claim(self):
        finding = self.by_id["SBX-STORE-LOCATOR-MOBILE-THIRD-PARTY-ERROR-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ALLOW")
        self.assertEqual(finding["decision"]["status"], "CONFIRMED")
        self.assertEqual(finding["decision"]["severity"], "P2")
        self.assertEqual(finding["user_control"]["risk"], "MEDIUM")
        self.assertEqual(finding["evidence"]["counterfactual"]["provider_identity"], "UNKNOWN")

    def test_authority_remains_audit_only(self):
        authority = self.packet["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for grant in ("ownership", "approval", "execution", "delivery", "deployment", "merge"):
            self.assertIs(authority[grant], False)

    def test_packet_is_deterministic(self):
        second = module.build_packet(self.contract, self.findings)
        self.assertEqual(self.packet, second)
        self.assertEqual(len(self.packet["packet_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
