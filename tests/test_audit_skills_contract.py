from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/validate_audit_skills.py"
SPEC = importlib.util.spec_from_file_location("validate_audit_skills", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class AuditSkillContractTests(unittest.TestCase):
    def test_repository_contract_is_valid(self) -> None:
        self.assertEqual([], validator.validate_repository())

    def test_wrong_skill_name_fails_closed(self) -> None:
        original = (ROOT / "skills/evidence-capture/SKILL.md").read_text(encoding="utf-8")
        mutated = original.replace("name: evidence-capture", "name: unsafe-capture", 1)
        errors = validator.validate_skill_text("evidence-capture", mutated)
        self.assertTrue(any("frontmatter name" in error for error in errors), errors)

    def test_missing_uncertainty_state_is_rejected(self) -> None:
        body = ("Evidence and authority boundaries must remain explicit. " * 20).strip()
        text = (
            "---\n"
            "name: synthetic-skill\n"
            "description: A synthetic skill used to prove that missing fail-closed states are rejected.\n"
            "---\n"
            f"{body}\n"
        )
        errors = validator.validate_skill_text("synthetic-skill", text)
        self.assertTrue(any("uncertainty/fail-closed" in error for error in errors), errors)

    def test_schema_without_not_run_is_rejected(self) -> None:
        schema_path = ROOT / "schemas/causal-deep-audit-packet.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["properties"]["verdict"]["properties"]["state"]["enum"].remove("NOT_RUN")
        errors = validator.validate_schema(schema)
        self.assertTrue(any("NOT_RUN" in error for error in errors), errors)

    def test_schema_cannot_expand_gate_authority(self) -> None:
        schema_path = ROOT / "schemas/causal-deep-audit-packet.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["properties"]["verdict"]["properties"]["gate"]["enum"].append("MERGE")
        errors = validator.validate_schema(schema)
        self.assertTrue(any("ALLOW_REPORT/ESCALATE/BLOCK" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
