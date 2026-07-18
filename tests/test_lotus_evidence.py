import copy
import importlib.util
import json
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
        """Load a fresh copy of the repository fixture for every test."""
        with validator.RUN_PATH.open(encoding="utf-8") as handle:
            self.run = json.load(handle)

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


if __name__ == "__main__":
    unittest.main()
