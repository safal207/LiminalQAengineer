from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/validate_audit_skills.py"
SPEC = importlib.util.spec_from_file_location("validate_audit_skills", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

CYBER_SOURCES = ROOT / "skills/cyber-causal-audit/sources.json"
CYBER_AUDIT = ROOT / "audits/security/tradernet-repository-causal-review-v1.json"
CYBER_SKILL = ROOT / "skills/cyber-causal-audit/SKILL.md"
WS_SKILL = ROOT / "skills/websocket-redis-lifecycle/SKILL.md"
CYBER_REPORT = ROOT / "docs/audits/TRADERNET_REPOSITORY_CYBER_CAUSAL_REVIEW.md"


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
        schema["properties"]["verdict"]["properties"]["state"]["enum"].remove(
            "NOT_RUN"
        )
        errors = validator.validate_schema(schema)
        self.assertTrue(any("NOT_RUN" in error for error in errors), errors)

    def test_schema_cannot_expand_gate_authority(self) -> None:
        schema_path = ROOT / "schemas/causal-deep-audit-packet.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["properties"]["verdict"]["properties"]["gate"]["enum"].append(
            "MERGE"
        )
        errors = validator.validate_schema(schema)
        self.assertTrue(any("ALLOW_REPORT/ESCALATE/BLOCK" in error for error in errors), errors)

    def test_external_skill_execution_cannot_be_enabled_silently(self) -> None:
        sources = json.loads(CYBER_SOURCES.read_text(encoding="utf-8"))
        sources["adoption_policy"]["remote_runtime_execution"] = True
        errors = validator.validate_cyber_sources(sources)
        self.assertTrue(any("remote runtime execution" in error for error in errors), errors)

    def test_mutable_external_source_pin_is_rejected(self) -> None:
        sources = json.loads(CYBER_SOURCES.read_text(encoding="utf-8"))
        sources["method_sources"][0]["commit"] = "main"
        errors = validator.validate_cyber_sources(sources)
        self.assertTrue(any("exact commit" in error for error in errors), errors)

    def test_external_executable_dependency_is_rejected(self) -> None:
        sources = json.loads(CYBER_SOURCES.read_text(encoding="utf-8"))
        sources["method_sources"][0]["adoption"] = "EXECUTABLE_DEPENDENCY"
        errors = validator.validate_cyber_sources(sources)
        self.assertTrue(any("executable" in error for error in errors), errors)

    def test_security_finding_cannot_skip_competing_explanation(self) -> None:
        audit = json.loads(CYBER_AUDIT.read_text(encoding="utf-8"))
        audit["findings"][0]["competing_explanations"] = []
        errors = validator.validate_cyber_audit(audit)
        self.assertTrue(any("competing explanations" in error for error in errors), errors)

    def test_security_finding_cannot_claim_confirmation_from_static_review(self) -> None:
        audit = json.loads(CYBER_AUDIT.read_text(encoding="utf-8"))
        audit["findings"][0]["claim_level"] = "CONFIRMED_VULNERABILITY"
        errors = validator.validate_cyber_audit(audit)
        self.assertTrue(any("overstates" in error for error in errors), errors)

    def test_credential_and_financial_boundaries_are_mandatory(self) -> None:
        audit = json.loads(CYBER_AUDIT.read_text(encoding="utf-8"))
        audit["authority"]["prohibited"].remove("use credentials")
        audit["authority"]["prohibited"].remove("place or cancel orders")
        errors = validator.validate_cyber_audit(audit)
        self.assertTrue(any("use credentials" in error for error in errors), errors)
        self.assertTrue(any("place or cancel orders" in error for error in errors), errors)

    def test_skills_and_report_contain_no_embedded_secret_values(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (CYBER_SKILL, WS_SKILL, CYBER_SOURCES, CYBER_AUDIT, CYBER_REPORT)
        )
        forbidden_patterns = {
            "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "bearer": r"(?i)bearer\s+[A-Za-z0-9._~+/-]{16,}",
            "cookie_value": r"(?i)(?:cookie|sid|session)\s*[:=]\s*[A-Za-z0-9._~+/-]{20,}",
            "api_key_value": r"(?i)(?:api[_-]?key|api[_-]?secret)\s*[:=]\s*[A-Za-z0-9._~+/-]{16,}",
        }
        for name, pattern in forbidden_patterns.items():
            self.assertIsNone(re.search(pattern, combined), name)

    def test_analog_repository_boundary_is_explicit(self) -> None:
        audit = json.loads(CYBER_AUDIT.read_text(encoding="utf-8"))
        self.assertTrue(
            audit["claim_policy"]["analog_repository_is_not_tradernet_internal_code"]
        )
        report = CYBER_REPORT.read_text(encoding="utf-8")
        self.assertIn(
            "not evidence that Tradernet uses the same internal implementation",
            report,
        )


if __name__ == "__main__":
    unittest.main()
