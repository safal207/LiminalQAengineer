from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CYBER_SKILL = ROOT / "skills" / "cyber-causal-audit" / "SKILL.md"
CYBER_SPEC = ROOT / "skills" / "cyber-causal-audit" / "SPEC.md"
WS_SKILL = ROOT / "skills" / "websocket-redis-lifecycle" / "SKILL.md"
SOURCES = ROOT / "skills" / "cyber-causal-audit" / "sources.json"
AUDIT = ROOT / "audits" / "security" / "tradernet-repository-causal-review-v1.json"
REPORT = ROOT / "docs" / "audits" / "TRADERNET_REPOSITORY_CYBER_CAUSAL_REVIEW.md"
ORCHESTRATOR = ROOT / "skills" / "causal-deep-audit" / "SKILL.md"


class CyberCausalAuditContractTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        for path in (
            CYBER_SKILL,
            CYBER_SPEC,
            WS_SKILL,
            SOURCES,
            AUDIT,
            REPORT,
            ORCHESTRATOR,
        ):
            self.assertTrue(path.is_file(), path)

    def test_skill_frontmatter_and_routes(self) -> None:
        cyber = CYBER_SKILL.read_text(encoding="utf-8")
        ws = WS_SKILL.read_text(encoding="utf-8")
        orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")

        self.assertRegex(cyber, r"(?m)^name: cyber-causal-audit$")
        self.assertRegex(ws, r"(?m)^name: websocket-redis-lifecycle$")
        self.assertIn("cyber-causal-audit", orchestrator)
        self.assertIn("websocket-redis-lifecycle", cyber)

    def test_security_methods_are_fail_closed(self) -> None:
        cyber = CYBER_SKILL.read_text(encoding="utf-8")
        ws = WS_SKILL.read_text(encoding="utf-8")
        sources = json.loads(SOURCES.read_text(encoding="utf-8"))

        for required in (
            "exact commit SHA",
            "license",
            "scan `SKILL.md`, scripts, references, hooks, and manifests",
            "false-positive gate",
            "Rationalizations to reject",
            "Missing authority narrows the audit",
        ):
            self.assertIn(required, cyber)

        for required in (
            "Identity domains",
            "Add/remove symmetry",
            "Generation fencing",
            "Multi-socket cardinality",
            "Exactly-once delivery intent",
            "Heartbeat and cleanup",
            "two sockets",
        ):
            self.assertIn(required, ws)

        # Explanatory prose may name a dangerous pattern such as `curl | sh`.
        # The enforceable contract is that no upstream skill or mutable remote
        # payload is enabled as an executable dependency.
        self.assertFalse(sources["adoption_policy"]["remote_runtime_execution"])
        self.assertFalse(sources["adoption_policy"]["mutable_branch_execution"])
        self.assertTrue(
            all(
                entry["adoption"] != "EXECUTABLE_DEPENDENCY"
                for entry in sources["method_sources"]
            )
        )

    def test_external_sources_are_exactly_pinned_and_non_executable(self) -> None:
        payload = json.loads(SOURCES.read_text(encoding="utf-8"))
        self.assertFalse(payload["adoption_policy"]["remote_runtime_execution"])
        self.assertFalse(payload["adoption_policy"]["mutable_branch_execution"])

        expected_sources = {
            "openai/skills",
            "trailofbits/skills",
            "getsentry/skills",
            "semgrep/skills",
            "anthropics/skills",
        }
        actual_sources = {entry["repository"] for entry in payload["method_sources"]}
        self.assertEqual(expected_sources, actual_sources)

        for entry in payload["method_sources"]:
            self.assertRegex(entry["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(entry["license"])
            self.assertTrue(entry["license_path"])
            self.assertNotEqual(entry["adoption"], "EXECUTABLE_DEPENDENCY")

        runtime_repositories = {
            entry["repository"] for entry in payload["runtime_compatibility_references"]
        }
        self.assertEqual(
            runtime_repositories,
            {"QwenLM/qwen-code", "MoonshotAI/kimi-cli", "xai-org/grok-build"},
        )
        for entry in payload["runtime_compatibility_references"]:
            self.assertRegex(entry["commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(entry["adoption"], "NO_CODE_OR_PROMPT_COPY")

    def test_audit_preserves_claim_boundaries(self) -> None:
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["status"], "STATIC_REVIEW_COMPLETE_RUNTIME_VALIDATION_PENDING"
        )
        self.assertIn("use credentials", payload["authority"]["prohibited"])
        self.assertIn("place or cancel orders", payload["authority"]["prohibited"])
        self.assertIn(
            "mass subscribe or load test production", payload["authority"]["prohibited"]
        )
        self.assertTrue(
            payload["claim_policy"]["analog_repository_is_not_tradernet_internal_code"]
        )
        self.assertTrue(
            payload["claim_policy"]["static_candidate_requires_runtime_discriminator"]
        )

        allowed_levels = {
            "OBSERVATION",
            "SECURITY_SIGNAL",
            "DEFECT_CANDIDATE",
            "RESOURCE_LEAK_CANDIDATE",
        }
        finding_ids: set[str] = set()
        for finding in payload["findings"]:
            self.assertNotIn(finding["id"], finding_ids)
            finding_ids.add(finding["id"])
            self.assertIn(finding["claim_level"], allowed_levels)
            self.assertIn(finding["severity"], {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
            self.assertIn(finding["confidence"], {"LOW", "MEDIUM", "HIGH"})
            self.assertTrue(finding["observation"])
            self.assertTrue(finding["invariant"])
            self.assertTrue(finding["causal_hypothesis"])
            self.assertTrue(finding["competing_explanations"])
            self.assertTrue(finding["next_test"])

        self.assertIn("CYB-WS-002", finding_ids)
        self.assertIn("CYB-WS-004", finding_ids)
        self.assertIn("CYB-TOOL-001", finding_ids)
        self.assertIn("CYB-API-001", finding_ids)
        self.assertIn("TN-DATA-001", finding_ids)

    def test_repository_evidence_is_exactly_identified(self) -> None:
        payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        expected = {
            "safal207/Liminal": "426bf5c41a6215b0fef1e9ca59df00a880491c14",
            "safal207/Proto-liminal": "ba32132618121cf8564db7367394fb59d818b675",
            "safal207/test_qorer_f": "4fe50bfa9007f142704b22666a976fdd0b5af4f6",
            "safal207/LiminalQAengineer": "5f0c82162d6cd37c6971a935c988d5008f34dd43",
        }
        actual = {
            entry["repository"]: entry["commit"] for entry in payload["repositories"]
        }
        self.assertEqual(expected, actual)
        for commit in actual.values():
            self.assertRegex(commit, r"^[0-9a-f]{40}$")

    def test_no_secret_values_are_embedded(self) -> None:
        checked = [CYBER_SKILL, CYBER_SPEC, WS_SKILL, SOURCES, AUDIT, REPORT]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in checked)

        forbidden_patterns = {
            "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "bearer": r"(?i)bearer\s+[A-Za-z0-9._~+/-]{16,}",
            "cookie_value": r"(?i)(?:cookie|sid|session)\s*[:=]\s*[A-Za-z0-9._~+/-]{20,}",
            "api_key_value": r"(?i)(?:api[_-]?key|api[_-]?secret)\s*[:=]\s*[A-Za-z0-9._~+/-]{16,}",
        }
        for name, pattern in forbidden_patterns.items():
            self.assertIsNone(re.search(pattern, combined), name)

    def test_report_keeps_advisory_authority(self) -> None:
        report = REPORT.read_text(encoding="utf-8")
        self.assertIn("HUMAN_REVIEW_REQUIRED", report)
        self.assertIn(
            "not evidence that Tradernet uses the same internal implementation",
            report,
        )
        self.assertIn("No real endpoint call is needed", report)
        self.assertIn("no real credentials", report)


if __name__ == "__main__":
    unittest.main()
