from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lotus_liminaldb_memory.py"
spec = importlib.util.spec_from_file_location("lotus_liminaldb_memory", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def authority():
    return {
        "mode": "audit_only",
        "ownership": False,
        "approval": False,
        "execution": False,
        "delivery": False,
        "deployment": False,
        "merge": False,
    }


def packet(status="CONFIRMED", finding_sha="a" * 64, verdict="ALLOW", cml="PROPOSED_SINGLE"):
    auth = authority()
    return {
        "schema_version": module.PACKET_SCHEMA,
        "packet_id": "lotus-test-v0.1",
        "repository": "safal207/LiminalQAengineer",
        "source_branch": "agent/lotus-test",
        "packet_sha256": "b" * 64,
        "authority": auth,
        "findings": [
            {
                "finding_id": "TEST-001",
                "packet_sha256": finding_sha,
                "domain": "example.test",
                "surface": "public",
                "judgment": {"verdict": verdict},
                "causal_memory": {
                    "canonical_id": "test.causal.signature",
                    "status": cml,
                    "recurrence": "single",
                    "durable_memory": False,
                },
                "user_control": {"risk": "LOW"},
                "decision": {
                    "status": status,
                    "severity": "P2" if status == "CONFIRMED" else "UNASSIGNED",
                    "confidence": "HIGH",
                },
                "evidence": {
                    "state": "exact",
                    "source_path": "evidence.json",
                    "bounded": True,
                    "replayable": True,
                },
                "authority": auth,
            }
        ],
    }


class LotusLiminalDBMemoryTest(unittest.TestCase):
    def test_export_is_deterministic_and_pins_liminaldb_contract(self):
        first = module.export_events(packet(), "2026-07-19T12:00:00+03:00", "1" * 40)
        second = module.export_events(packet(), "2026-07-19T12:00:00+03:00", "1" * 40)
        self.assertEqual(first, second)
        event = first[0]
        self.assertEqual(event["kind"], "audit")
        self.assertEqual(event["action"], "lotus.finding.observed")
        self.assertEqual(event["details"]["adapter"]["commit"], module.LIMINALDB_COMMIT)
        self.assertEqual(
            event["details"]["adapter"]["contract_blob_sha"],
            module.LIMINALDB_CONTRACT_BLOB_SHA,
        )
        self.assertEqual(event["id"], "lotus-0fcf3f1650c29997cf4d9bafc1ed17cd")

    def test_authority_and_pending_memory_are_preserved(self):
        event = module.export_events(packet(), "2026-07-19T12:00:00Z", "2" * 40)[0]
        for grant in module.AUTHORITY_GRANTS:
            self.assertIs(event["details"]["authority"][grant], False)
        self.assertIs(event["details"]["finding"]["durable_memory"], False)
        self.assertEqual(event["details"]["adapter"]["write_mode"], "artifact_only")

    def test_append_is_idempotent(self):
        events = module.export_events(packet(), "2026-07-19T12:00:00Z", "3" * 40)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            self.assertEqual(module.write_jsonl(path, events, append=True), 1)
            self.assertEqual(module.write_jsonl(path, events, append=True), 0)
            self.assertEqual(len(module.parse_jsonl(path)), 1)

    def test_history_and_compare_detect_changed_form(self):
        before = module.export_events(packet(), "2026-07-19T12:00:00Z", "4" * 40)[0]
        after_packet = packet(finding_sha="c" * 64)
        after = module.export_events(after_packet, "2026-07-20T12:00:00Z", "5" * 40)[0]
        value = module.compare([after, before])
        self.assertEqual(value["transition_count"], 1)
        self.assertEqual(
            value["transitions"][0]["transition"],
            "STILL_PRESENT_IN_CHANGED_FORM",
        )
        history = module.history([after, before], "test.causal.signature", None)
        self.assertEqual(history["observation_count"], 2)
        self.assertEqual(history["observations"][0]["id"], before["id"])

    def test_invalid_authority_is_rejected(self):
        bad = copy.deepcopy(packet())
        bad["authority"]["merge"] = True
        with self.assertRaisesRegex(ValueError, "authority.merge must be false"):
            module.export_events(bad, "2026-07-19T12:00:00Z", "6" * 40)

    def test_jsonl_round_trip(self):
        events = module.export_events(packet(), "2026-07-19T12:00:00Z", "7" * 40)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            module.write_jsonl(path, events)
            self.assertEqual(module.parse_jsonl(path), events)
            for line in path.read_text(encoding="utf-8").splitlines():
                self.assertIsInstance(json.loads(line), dict)


if __name__ == "__main__":
    unittest.main()
