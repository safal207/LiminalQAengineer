#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "lotus_liminaldb_ledger.py"
spec = importlib.util.spec_from_file_location("lotus_liminaldb_ledger", MODULE_PATH)
assert spec and spec.loader
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def authority() -> dict:
    return {
        "mode": "audit_only",
        "ownership": False,
        "approval": False,
        "execution": False,
        "delivery": False,
        "deployment": False,
        "merge": False,
    }


def contract() -> dict:
    return {
        "schema_version": "liminalqa-lotus-liminaldb-bridge-v0.1",
        "liminaldb_source": {
            "repository": "safal207/LiminalDB",
            "commit": "75ef9f7f403a34c60aa2ceba4cb3c97870d73e77",
            "path": "liminal-db/crates/liminal-core/src/mirror.rs",
            "blob_sha": "b66ed1c6ecb6726eb59e3153d38d81a55a7eeca5",
            "rule": "append-only replayable timeline; deterministic order and hash lineage",
        },
        "event_types": [name for name, _ in ledger.EVENT_ORDER],
        "authority": authority(),
    }


def packet() -> dict:
    value = {
        "schema_version": "liminalqa-lotus-decision-packet-v0.1",
        "packet_id": "sample-packet",
        "repository": "safal207/LiminalQAengineer",
        "source_branch": "agent/sample",
        "scope": "bounded public QA evidence",
        "contract": {},
        "summary": {},
        "findings": [
            {
                "finding_id": "B-002",
                "evidence": {"state": "conflicting"},
                "judgment": {"verdict": "ESCALATE"},
                "causal_memory": {"canonical_id": "b", "status": "CONFLICT"},
                "user_control": {"risk": "UNKNOWN"},
                "decision": {"status": "NEEDS_EVIDENCE"},
            },
            {
                "finding_id": "A-001",
                "evidence": {"state": "exact"},
                "judgment": {"verdict": "ALLOW"},
                "causal_memory": {"canonical_id": "a", "status": "PROPOSED_SINGLE"},
                "user_control": {"risk": "MEDIUM"},
                "decision": {"status": "CONFIRMED"},
            },
        ],
        "authority": authority(),
        "limitations": [],
    }
    value["packet_sha256"] = ledger.sha256_json(value)
    return value


class LotusLiminalDbLedgerTests(unittest.TestCase):
    def test_deterministic_ledger_and_finding_sort(self) -> None:
        first = ledger.build_ledger(contract(), packet())
        second = ledger.build_ledger(contract(), packet())
        self.assertEqual(first, second)
        self.assertEqual(first[0]["finding_id"], "A-001")
        self.assertEqual(first[-1]["finding_id"], "B-002")
        self.assertEqual(len(first), 10)

    def test_hash_chain_and_event_order(self) -> None:
        events = ledger.build_ledger(contract(), packet())
        ledger.verify_ledger(events, contract(), packet())
        self.assertIsNone(events[0]["previous_event_sha256"])
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current["previous_event_sha256"], previous["event_sha256"])
        self.assertEqual(
            [event["event_type"] for event in events[:5]],
            [name for name, _ in ledger.EVENT_ORDER],
        )

    def test_snapshot_is_replayable(self) -> None:
        events = ledger.build_ledger(contract(), packet())
        snapshot = ledger.build_snapshot(events, contract(), packet())
        self.assertEqual(snapshot["event_count"], 10)
        self.assertEqual(snapshot["finding_count"], 2)
        self.assertEqual(snapshot["findings"]["A-001"]["decision"]["status"], "CONFIRMED")
        self.assertEqual(snapshot["ledger_head_sha256"], events[-1]["event_sha256"])

    def test_tampered_event_is_rejected(self) -> None:
        events = ledger.build_ledger(contract(), packet())
        tampered = copy.deepcopy(events)
        tampered[3]["payload"]["risk"] = "LOW"
        with self.assertRaisesRegex(ValueError, "event hash mismatch"):
            ledger.verify_ledger(tampered, contract(), packet())

    def test_authority_drift_is_rejected(self) -> None:
        bad = contract()
        bad["authority"]["execution"] = True
        with self.assertRaisesRegex(ValueError, "authority.execution"):
            ledger.build_ledger(bad, packet())

    def test_packet_tamper_is_rejected(self) -> None:
        bad = packet()
        bad["findings"][0]["decision"]["status"] = "CONFIRMED"
        with self.assertRaisesRegex(ValueError, "packet_sha256"):
            ledger.build_ledger(contract(), bad)

    def test_outputs_replay(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "output"
            events = ledger.build_ledger(contract(), packet())
            snapshot = ledger.build_snapshot(events, contract(), packet())
            ledger.write_outputs(output, events, snapshot)
            replayed = ledger.read_jsonl(output / "lotus-ledger.jsonl")
            ledger.verify_ledger(replayed, contract(), packet())
            self.assertEqual(
                ledger.load_json(output / "lotus-ledger-snapshot.json"),
                ledger.build_snapshot(replayed, contract(), packet()),
            )


if __name__ == "__main__":
    unittest.main()
