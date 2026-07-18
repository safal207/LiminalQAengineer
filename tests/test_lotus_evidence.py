from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/validate_lotus_evidence.py"
SPEC = importlib.util.spec_from_file_location("validate_lotus_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class LotusEvidenceContractTests(unittest.TestCase):
    """Protect the evidence, judgment, trace, and storage invariants."""

    def setUp(self) -> None:
        """Load fresh repository fixtures for every test."""
        with validator.RUN_PATH.open(encoding="utf-8") as handle:
            self.run = json.load(handle)
        with validator.MANIFEST_PATH.open(encoding="utf-8") as handle:
            self.manifest = json.load(handle)

    def test_repository_example_is_valid(self) -> None:
        """The checked-in vertical-slice example must satisfy all invariants."""
        validator.validate_all()

    def test_planned_run_cannot_claim_confirmed_defect(self) -> None:
        """A planned investigation cannot be promoted to a confirmed defect."""
        invalid = copy.deepcopy(self.run)
        invalid["lotus"]["pythia"]["confirmed_defect"] = True
        with self.assertRaisesRegex(
            validator.ContractError, "planned run cannot claim a confirmed defect"
        ):
            validator.validate_run(invalid)

    def test_claim_kinds_cannot_collapse_into_hypotheses(self) -> None:
        """Fact, observation, and hypothesis must remain distinct claim kinds."""
        invalid = copy.deepcopy(self.run)
        for claim in invalid["claims"]:
            claim["kind"] = "hypothesis"
        with self.assertRaisesRegex(
            validator.ContractError, "distinguish fact, observation, and hypothesis"
        ):
            validator.validate_run(invalid)

    def test_storage_projection_must_be_append_only(self) -> None:
        """The LiminalDB projection cannot silently become mutable."""
        invalid = copy.deepcopy(self.run)
        invalid["liminaldb_projection"]["append_only"] = False
        with self.assertRaisesRegex(
            validator.ContractError, "projection must be append-only"
        ):
            validator.validate_run(invalid)

    def test_duplicate_protocol_pin_is_rejected(self) -> None:
        """A duplicate protocol name cannot be hidden by set conversion."""
        invalid = copy.deepcopy(self.run)
        invalid["protocol_pins"].append(copy.deepcopy(invalid["protocol_pins"][0]))
        with self.assertRaisesRegex(validator.ContractError, "duplicate protocol pin"):
            validator.validate_run(invalid)

    def test_manifest_links_must_match_run_and_decision(self) -> None:
        """The loaded manifest must match the run ID, path, and DRP decision."""
        invalid = copy.deepcopy(self.manifest)
        invalid["bundle_id"] = "OTHER-RUN"
        with self.assertRaisesRegex(validator.ContractError, "bundle_id"):
            validator.validate_links(self.run, invalid)

        invalid = copy.deepcopy(self.manifest)
        invalid["decision_ref"] = "OTHER-DECISION"
        with self.assertRaisesRegex(validator.ContractError, "decision_ref"):
            validator.validate_links(self.run, invalid)

        invalid_run = copy.deepcopy(self.run)
        invalid_run["evidence_manifest"] = "integrations/lotus/examples/other.json"
        with self.assertRaisesRegex(validator.ContractError, "evidence_manifest"):
            validator.validate_links(invalid_run, self.manifest)

    def test_absolute_and_traversal_manifest_paths_are_rejected(self) -> None:
        """Manifest artifacts cannot be absolute or escape through parent traversal."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            absolute = {
                "integrity_only": True,
                "truth_claim": False,
                "artifacts": [{"path": "/tmp/outside", "sha256": "0" * 64}],
            }
            with self.assertRaisesRegex(validator.ContractError, "relative path"):
                validator.validate_manifest(absolute, root=root)

            traversal = copy.deepcopy(absolute)
            traversal["artifacts"][0]["path"] = "../outside"
            with self.assertRaisesRegex(validator.ContractError, "escapes repository root"):
                validator.validate_manifest(traversal, root=root)

    def test_external_symlink_manifest_path_is_rejected(self) -> None:
        """A symlink inside the root cannot point an artifact outside the root."""
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unsupported")
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as outside_raw:
            root = Path(raw)
            outside = Path(outside_raw) / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            link = root / "link.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            manifest = {
                "integrity_only": True,
                "truth_claim": False,
                "artifacts": [
                    {
                        "path": "link.txt",
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                ],
            }
            with self.assertRaisesRegex(validator.ContractError, "escapes repository root"):
                validator.validate_manifest(manifest, root=root)


if __name__ == "__main__":
    unittest.main()
