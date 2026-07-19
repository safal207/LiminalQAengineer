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


class StarbucksLotusPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "standards/lotus-qa/lotus-qa-contract-v0.1.json").read_text(encoding="utf-8")
        )
        cls.findings = json.loads(
            (ROOT / "audits/lotus/starbucks/starbucks-findings-v0.1.json").read_text(encoding="utf-8")
        )
        cls.evidence = json.loads(
            (ROOT / "audits/lotus/starbucks/starbucks-public-evidence-v0.1.json").read_text(encoding="utf-8")
        )
        cls.packet = module.build_packet(cls.contract, cls.findings)
        cls.by_id = {item["finding_id"]: item for item in cls.packet["findings"]}

    def test_scope_is_public_read_only_and_non_destructive(self):
        scope = self.evidence["scope"]
        self.assertEqual(scope["mode"], "public_read_only")
        for key in (
            "authentication",
            "account_creation",
            "orders_or_payments",
            "direct_application_api_calls",
            "credential_validation",
            "token_requests",
            "load_testing",
            "exploitation",
        ):
            self.assertIs(scope[key], False)

    def test_sensitive_security_evidence_is_not_published(self):
        boundary = self.evidence["disclosure_boundary"]
        self.assertIs(boundary["public_repository"], True)
        self.assertIs(boundary["raw_secret_stored"], False)
        self.assertIs(boundary["raw_secret_used"], False)
        self.assertIs(boundary["affected_careers_routes_published"], False)
        self.assertEqual(boundary["private_reference_id"], "SBX-PRIVATE-SEC-2026-07-19-001")

    def test_expected_three_way_lotus_decision(self):
        self.assertEqual(self.packet["summary"]["finding_count"], 6)
        self.assertEqual(
            self.packet["summary"]["pythia_verdicts"],
            {"ALLOW": 2, "BLOCK": 2, "ESCALATE": 2},
        )
        self.assertEqual(
            self.packet["summary"]["decision_statuses"],
            {"BLOCKED": 2, "CONFIRMED": 2, "NEEDS_EVIDENCE": 2},
        )
        self.assertEqual(
            self.packet["summary"]["user_control_risks"],
            {"HIGH": 1, "LOW": 1, "MEDIUM": 1, "NONE": 2, "UNKNOWN": 1},
        )

    def test_private_credential_signal_cannot_receive_public_severity(self):
        finding = self.by_id["SBX-SEC-PUBLIC-CREDENTIAL-SIGNAL-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ESCALATE")
        self.assertEqual(finding["decision"]["status"], "NEEDS_EVIDENCE")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["user_control"]["risk"], "HIGH")
        self.assertEqual(finding["causal_memory"]["status"], "CONFLICT")
        self.assertEqual(
            finding["evidence"]["private_reference_id"],
            self.evidence["disclosure_boundary"]["private_reference_id"],
        )

    def test_javascript_dependency_is_confirmed_but_not_wcag_verdict(self):
        behavior = self.by_id["SBX-WEB-JS-DEPENDENCY-001"]
        self.assertEqual(behavior["judgment"]["verdict"], "ALLOW")
        self.assertEqual(behavior["decision"]["status"], "CONFIRMED")
        self.assertEqual(behavior["decision"]["severity"], "P2")
        self.assertEqual(behavior["user_control"]["risk"], "MEDIUM")

        wcag = self.by_id["SBX-A11Y-NOJS-WCAG-HYPOTHESIS-001"]
        self.assertEqual(wcag["judgment"]["verdict"], "BLOCK")
        self.assertEqual(wcag["decision"]["status"], "BLOCKED")
        self.assertEqual(wcag["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(wcag["causal_memory"]["status"], "NEGATIVE_CAUSAL_MEMORY")

    def test_sitemap_duplicates_are_confirmed_low_risk(self):
        finding = self.by_id["SBX-SEO-SITEMAP-DUPLICATES-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ALLOW")
        self.assertEqual(finding["decision"]["status"], "CONFIRMED")
        self.assertEqual(finding["decision"]["severity"], "P3")
        self.assertEqual(finding["user_control"]["risk"], "LOW")

    def test_accessibility_candidate_remains_without_severity(self):
        finding = self.by_id["SBX-A11Y-DUPLICATE-NAV-CANDIDATE-001"]
        self.assertEqual(finding["judgment"]["verdict"], "ESCALATE")
        self.assertEqual(finding["decision"]["status"], "NEEDS_EVIDENCE")
        self.assertEqual(finding["decision"]["severity"], "UNASSIGNED")
        self.assertEqual(finding["user_control"]["risk"], "UNKNOWN")

    def test_active_exploit_claim_is_negative_memory(self):
        finding = self.by_id["SBX-SEC-ACTIVE-EXPLOIT-HYPOTHESIS-001"]
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
