from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/sitnikov-inspired-self-regulation/SKILL.md"
SOURCES = ROOT / "skills/sitnikov-inspired-self-regulation/sources.json"
INDEX = ROOT / "docs/research/ALEXEY_SITNIKOV_PUBLICATIONS_INDEX.md"


class SitnikovInspiredSelfRegulationSkillContract(unittest.TestCase):
    def test_skill_files_exist(self) -> None:
        self.assertTrue(SKILL.is_file())
        self.assertTrue(SOURCES.is_file())
        self.assertTrue(INDEX.is_file())

    def test_skill_has_identity_and_originality_boundary(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("name: sitnikov-inspired-self-regulation", text)
        self.assertIn("not authorised or endorsed by Alexey Sitnikov", text)
        self.assertIn("original synthesis", text.lower())
        self.assertIn("claim to be Alexey Sitnikov", text)
        self.assertIn("official session", text)

    def test_skill_fails_closed_on_high_risk_requests(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        for required in (
            "blocked_by_safety",
            "driving",
            "recover",
            "memories",
            "trauma",
            "harm self or others",
            "local emergency services",
            "human_clinician_recommended",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_skill_preserves_agency_and_reorientation(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        for required in (
            "the user remains the decision-maker",
            "stop immediately",
            "full reorientation",
            "open or refocus the eyes",
            "one next action",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_skill_separates_author_frame_from_clinical_evidence(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for label in (
            "AUTHOR_FRAME",
            "BIBLIOGRAPHIC_RECORD",
            "CLINICAL_EVIDENCE",
            "ORIGINAL_SYNTHESIS",
            "NEEDS_EVIDENCE",
            "CONTESTED_OR_LIMITED",
        ):
            with self.subTest(label=label):
                self.assertIn(label, text)
        self.assertIn(
            "Do not turn an `AUTHOR_FRAME` into `CLINICAL_EVIDENCE`",
            text,
        )

    def test_source_registry_is_machine_readable_and_honest(self) -> None:
        registry = json.loads(SOURCES.read_text(encoding="utf-8"))
        self.assertEqual(registry["schema_version"], "1.0")
        self.assertEqual(
            registry["completeness"]["state"],
            "PARTIAL_BUT_VERIFIED",
        )
        self.assertIn("does not claim", registry["completeness"]["statement"])
        self.assertGreaterEqual(len(registry["verified_publications"]), 15)
        self.assertGreaterEqual(len(registry["clinical_boundary_sources"]), 4)

    def test_unresolved_bibliography_stays_unresolved(self) -> None:
        registry = json.loads(SOURCES.read_text(encoding="utf-8"))
        publications = {
            entry["id"]: entry for entry in registry["verified_publications"]
        }
        self.assertEqual(publications["PUB-BANKING"]["status"], "NEEDS_EVIDENCE")
        self.assertEqual(
            publications["PUB-KARMAGUIDE"]["status"],
            "ANNOUNCED_NOT_CONFIRMED_PUBLISHED",
        )
        self.assertEqual(
            publications["PUB-KARMAPOWER"]["status"],
            "PUBLISHER_CATALOGUE_ENTRY",
        )

    def test_index_rejects_magic_and_universal_efficacy_claims(self) -> None:
        text = INDEX.read_text(encoding="utf-8")
        self.assertIn(
            "не как независимое доказательство универсальных «законов судьбы»",
            text,
        )
        self.assertIn("метафора «перепрошивки мозга»", text)
        self.assertIn("самогипноз заменяет диагностику", text)


if __name__ == "__main__":
    unittest.main()
