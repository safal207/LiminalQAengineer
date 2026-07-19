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
                "run_id": 29666251111,
                "head_sha": "4d58d54db49a8ef43260c7f5c4a2ac683c8e865f",
                "artifact_sha256": "65fc7473982cca5ea2071b7219390b70824fb3613b8f1d59e32c918f71d7ca67",
                "result": "NO_FIRST_PARTY_WEBSOCKET_OBSERVED",
            },
        )
        self.assertEqual(
            evidence["duplicate-settings"],
            {
                "id": "duplicate-settings",
                "run_id": 29666496587,
                "head_sha": "6d22575cf4cca307508614d1eb6c6bfd3e5ee62d",
                "artifact_sha256": "20f5d9fd464b63a1f65a54636129ccdb7c16b0a801ea9557efc1791a39b55088",
                "result": "CONFIRMED_REDUNDANT_DUPLICATE_REQUEST",
            },
        )


if __name__ == "__main__":
    unittest.main()
