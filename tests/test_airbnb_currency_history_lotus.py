from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = (
    ROOT
    / "audits"
    / "lotus"
    / "airbnb"
    / "airbnb-currency-history-result-v0.1.json"
)
EXPECTED_PACKET_SHA256 = (
    "e89f580c251c707735a55689c56fa8d787b14cbe51124e2ac0ccd701cd495989"
)


class AirbnbCurrencyHistoryLotusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = PACKET_PATH.read_bytes()
        cls.packet = json.loads(cls.raw)
        cls.findings = {
            finding["id"]: finding for finding in cls.packet["findings"]
        }

    def test_exact_source_and_packet_identity(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.raw).hexdigest(), EXPECTED_PACKET_SHA256
        )
        self.assertEqual(self.packet["source"]["execution_pr"], 77)
        self.assertEqual(
            self.packet["source"]["execution_head"],
            "404da0d714de334e18080138623370fdc32717f5",
        )
        self.assertEqual(self.packet["source"]["workflow_run_id"], 29678020284)
        self.assertEqual(
            self.packet["source"]["classifier_revision"],
            "target-price-context-v2",
        )

    def test_summary_does_not_invent_a_defect(self) -> None:
        summary = self.packet["summary"]
        self.assertEqual(summary["listings"], 3)
        self.assertEqual(summary["fresh_contexts"], 6)
        self.assertEqual(summary["consistent_attempts"], 2)
        self.assertEqual(summary["inconclusive_attempts"], 4)
        self.assertEqual(summary["inconsistent_attempts"], 0)
        self.assertEqual(summary["confirmed_defects"], 0)
        self.assertEqual(summary["payments_submitted"], 0)
        self.assertEqual(summary["reservations_created"], 0)
        self.assertEqual(
            summary["decision_counts"],
            {"NO_DEFECT_OBSERVED": 1, "NEEDS_EVIDENCE": 2, "BLOCKED": 1},
        )

    def test_valid_antalya_result_is_bounded_negative_memory(self) -> None:
        finding = self.findings[
            "ABNB-ANTALYA-CURRENCY-HISTORY-NEGATIVE-CONTROL-001"
        ]
        self.assertEqual(finding["decision"], "NO_DEFECT_OBSERVED")
        self.assertEqual(finding["pythia"], "ALLOW_BOUNDED_NEGATIVE_RESULT")
        self.assertEqual(finding["cml"], "NEGATIVE_CAUSAL_MEMORY")
        self.assertEqual(finding["ls"], "NONE")
        self.assertEqual(finding["severity"], "UNASSIGNED")
        self.assertEqual(
            finding["evidence"]["attempt_outcomes"],
            ["consistent", "consistent"],
        )
        self.assertEqual(
            finding["evidence"]["normalized_signatures"],
            [["TRY", "EUR", "TRY", "EUR"], ["TRY", "EUR", "TRY", "EUR"]],
        )
        self.assertEqual(finding["evidence"]["http_4xx_5xx"], 0)
        self.assertEqual(finding["evidence"]["console_errors"], 0)

    def test_inconclusive_listings_remain_needs_evidence(self) -> None:
        for finding_id in (
            "ABNB-ALANYA-CENTER-CURRENCY-HISTORY-001",
            "ABNB-ALANYA-BEACH-CURRENCY-HISTORY-001",
        ):
            finding = self.findings[finding_id]
            self.assertEqual(finding["decision"], "NEEDS_EVIDENCE")
            self.assertEqual(finding["pythia"], "ESCALATE")
            self.assertEqual(finding["cml"], "CONFLICT")
            self.assertEqual(finding["ls"], "UNKNOWN")
            self.assertEqual(finding["severity"], "UNASSIGNED")
            self.assertEqual(
                finding["evidence"]["attempt_outcomes"],
                ["inconclusive", "inconclusive"],
            )

    def test_broad_cross_listing_bug_claim_is_blocked(self) -> None:
        finding = self.findings[
            "ABNB-CURRENCY-HISTORY-CROSS-LISTING-DEFECT-001"
        ]
        self.assertEqual(finding["decision"], "BLOCKED")
        self.assertEqual(finding["pythia"], "BLOCK")
        self.assertEqual(finding["cml"], "NEGATIVE_CAUSAL_MEMORY")
        self.assertEqual(finding["severity"], "UNASSIGNED")
        self.assertEqual(finding["evidence"]["inconsistent_attempts"], 0)

    def test_authority_boundary_remains_false(self) -> None:
        authority = self.packet["authority"]
        self.assertEqual(authority["mode"], "audit_only")
        for key in (
            "ownership",
            "approval",
            "execution",
            "delivery",
            "external_submission",
            "merge",
        ):
            self.assertIs(authority[key], False)


if __name__ == "__main__":
    unittest.main()
