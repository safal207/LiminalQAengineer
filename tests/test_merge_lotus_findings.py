#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "merge_lotus_findings.py"
spec = importlib.util.spec_from_file_location("merge_lotus_findings", MODULE_PATH)
assert spec and spec.loader
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


def document(packet_id: str, finding_id: str, repository: str = "safal207/LiminalQAengineer") -> dict:
    return {
        "schema_version": "liminalqa-lotus-findings-v0.1",
        "packet_id": packet_id,
        "repository": repository,
        "source_branch": f"agent/{packet_id}",
        "scope": f"scope for {packet_id}",
        "findings": [{"id": finding_id}],
    }


class MergeLotusFindingsTests(unittest.TestCase):
    def test_deterministic_merge_and_sort(self) -> None:
        first = merge.merge_documents(
            [document("b", "Z-002"), document("a", "A-001")],
            packet_id="combined",
            source_branch="agent/combined",
            scope="combined scope",
        )
        second = merge.merge_documents(
            [document("b", "Z-002"), document("a", "A-001")],
            packet_id="combined",
            source_branch="agent/combined",
            scope="combined scope",
        )
        self.assertEqual(first, second)
        self.assertEqual([finding["id"] for finding in first["findings"]], ["A-001", "Z-002"])
        self.assertEqual([item["packet_id"] for item in first["source_packets"]], ["a", "b"])

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate finding ids"):
            merge.merge_documents(
                [document("a", "A-001"), document("b", "A-001")],
                packet_id="combined",
                source_branch="agent/combined",
                scope="combined scope",
            )

    def test_repository_drift_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "same repository"):
            merge.merge_documents(
                [
                    document("a", "A-001"),
                    document("b", "B-002", repository="other/repo"),
                ],
                packet_id="combined",
                source_branch="agent/combined",
                scope="combined scope",
            )

    def test_input_documents_are_not_mutated(self) -> None:
        inputs = [document("b", "Z-002"), document("a", "A-001")]
        before = copy.deepcopy(inputs)
        merge.merge_documents(
            inputs,
            packet_id="combined",
            source_branch="agent/combined",
            scope="combined scope",
        )
        self.assertEqual(inputs, before)


if __name__ == "__main__":
    unittest.main()
