from __future__ import annotations

import json
import unittest
from pathlib import Path


PACKET_PATH = (
    Path(__file__).resolve().parents[1]
    / "audits"
    / "lotus"
    / "tradernet"
    / "tradernet-connection-lotus-v0.1.json"
)


def load_packet() -> dict:
    return json.loads(PACKET_PATH.read_text(encoding="utf-8"))


class TradernetConnectionLotusContractTest(unittest.TestCase):
    def test_only_duplicate_settings_is_confirmed(self) -> None:
        packet = load_packet()
        findings = {item["id"]: item for item in packet["findings"]}

        confirmed = [
            item["id"] for item in packet["findings"] if item["status"] == "CONFIRMED"
        ]
        self.assertEqual(confirmed, ["TRADERNET-PUBLIC-DUPLICATE-SETTINGS-001"])
        self.assertEqual(
            findings["TRADERNET-PUBLIC-ZOMBIE-WS-001"]["status"],
            "BLOCKED_NOT_TESTABLE",
        )
        self.assertEqual(
            findings["TRADERNET-PUBLIC-STALE-STATE-001"]["status"],
            "NEEDS_EVIDENCE",
        )
        self.assertEqual(
            findings["TRADERNET-PUBLIC-SETTINGS-POST-001"]["status"],
            "NEEDS_EVIDENCE",
        )

    def test_duplicate_request_evidence_is_exact_and_reproducible(self) -> None:
        packet = load_packet()
        finding = next(
            item
            for item in packet["findings"]
            if item["id"] == "TRADERNET-PUBLIC-DUPLICATE-SETTINGS-001"
        )
        reproduction = finding["reproduction"]

        self.assertEqual(finding["severity"], "P2_PERFORMANCE_RELIABILITY")
        self.assertEqual(reproduction["fresh_contexts"], 3)
        self.assertEqual(reproduction["matching_rounds"], 3)
        self.assertEqual(reproduction["requests_per_round"], 2)
        self.assertIs(reproduction["same_start_millisecond"], True)
        self.assertIs(reproduction["overlap"], True)
        self.assertIs(reproduction["http_200"], True)
        self.assertEqual(reproduction["resource_types"], ["Fetch", "XHR"])
        self.assertEqual(
            reproduction["identical_response_sha256"],
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        )
        self.assertEqual(
            reproduction["encoded_transfer_bytes_per_request_range"], [3463, 3465]
        )

    def test_settings_post_remains_observation_not_defect(self) -> None:
        packet = load_packet()
        finding = next(
            item
            for item in packet["findings"]
            if item["id"] == "TRADERNET-PUBLIC-SETTINGS-POST-001"
        )
        observed = finding["observed_only"]

        self.assertEqual(finding["status"], "NEEDS_EVIDENCE")
        self.assertEqual(finding["severity"], "UNASSIGNED")
        self.assertEqual(observed["matching_rounds"], 3)
        self.assertEqual(observed["request_body_bytes_min"], 33187)
        self.assertEqual(observed["request_body_bytes_max"], 33404)
        self.assertEqual(observed["http_status"], 200)
        self.assertEqual(observed["response_bytes"], 1)

    def test_lotus_and_authority_boundaries_remain_bounded(self) -> None:
        packet = load_packet()

        self.assertEqual(
            packet["pythia"]["verdicts"],
            {
                "TRADERNET-PUBLIC-DUPLICATE-SETTINGS-001": "ALLOW",
                "TRADERNET-PUBLIC-ZOMBIE-WS-001": "BLOCK",
                "TRADERNET-PUBLIC-STALE-STATE-001": "ESCALATE",
                "TRADERNET-PUBLIC-SETTINGS-POST-001": "ESCALATE",
            },
        )
        self.assertEqual(packet["cml"]["memory_mode"], "PROPOSE_ONLY")
        self.assertIs(packet["cml"]["durable_acceptance"], False)
        self.assertEqual(packet["liminaldb"]["write_mode"], "artifact_only")
        self.assertIs(packet["liminaldb"]["durable_memory"], False)
        self.assertEqual(
            packet["authority"],
            {
                "mode": "audit_only",
                "ownership": False,
                "approval": False,
                "execution": False,
                "delivery": False,
                "external_submission": False,
                "merge": False,
            },
        )

    def test_exact_evidence_runs_and_artifacts_are_pinned(self) -> None:
        packet = load_packet()
        evidence = {item["id"]: item for item in packet["evidence"]}

        self.assertEqual(
            evidence["connection-lifecycle"],
            {
                "id": "connection-lifecycle",
                "run_id": 29687311888,
                "head_sha": "89a13d3e98f811f07f56543265ca1a8399f79c65",
                "artifact_sha256": "9641cb67da53d947cf107d6ba0cb37eec2ee3fcc7f79c8f734a0d6948f1c953d",
                "result": "NO_FIRST_PARTY_WEBSOCKET_OBSERVED",
            },
        )
        self.assertEqual(
            evidence["duplicate-settings"],
            {
                "id": "duplicate-settings",
                "run_id": 29687311871,
                "head_sha": "89a13d3e98f811f07f56543265ca1a8399f79c65",
                "artifact_sha256": "0b7fb1232f828e72870951ebb44c5b4b6953a84d7fe5e3b93ab9a1b38c94ecb8",
                "result": "CONFIRMED_REDUNDANT_DUPLICATE_REQUEST",
            },
        )


if __name__ == "__main__":
    unittest.main()
