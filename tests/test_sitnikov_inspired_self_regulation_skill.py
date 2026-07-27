from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/sitnikov-inspired-self-regulation/SKILL.md"
SOURCES = ROOT / "skills/sitnikov-inspired-self-regulation/sources.json"
INDEX = ROOT / "docs/research/ALEXEY_SITNIKOV_PUBLICATIONS_INDEX.md"


def test_skill_files_exist() -> None:
    assert SKILL.is_file()
    assert SOURCES.is_file()
    assert INDEX.is_file()


def test_skill_has_identity_and_originality_boundary() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "name: sitnikov-inspired-self-regulation" in text
    assert "not authorised or endorsed by Alexey Sitnikov" in text
    assert "original synthesis" in text.lower()
    assert "claim to be Alexey Sitnikov" in text
    assert "official session" in text


def test_skill_fails_closed_on_high_risk_requests() -> None:
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
        assert required in text


def test_skill_preserves_agency_and_reorientation() -> None:
    text = SKILL.read_text(encoding="utf-8").lower()
    for required in (
        "the user remains the decision-maker",
        "stop immediately",
        "full reorientation",
        "open or refocus the eyes",
        "one next action",
    ):
        assert required in text


def test_skill_separates_author_frame_from_clinical_evidence() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for label in (
        "AUTHOR_FRAME",
        "BIBLIOGRAPHIC_RECORD",
        "CLINICAL_EVIDENCE",
        "ORIGINAL_SYNTHESIS",
        "NEEDS_EVIDENCE",
        "CONTESTED_OR_LIMITED",
    ):
        assert label in text
    assert "Do not turn an `AUTHOR_FRAME` into `CLINICAL_EVIDENCE`" in text


def test_source_registry_is_machine_readable_and_honest_about_completeness() -> None:
    registry = json.loads(SOURCES.read_text(encoding="utf-8"))
    assert registry["schema_version"] == "1.0"
    assert registry["completeness"]["state"] == "PARTIAL_BUT_VERIFIED"
    assert "does not claim" in registry["completeness"]["statement"]
    assert len(registry["verified_publications"]) >= 15
    assert len(registry["clinical_boundary_sources"]) >= 4


def test_unresolved_bibliography_stays_unresolved() -> None:
    registry = json.loads(SOURCES.read_text(encoding="utf-8"))
    publications = {entry["id"]: entry for entry in registry["verified_publications"]}
    assert publications["PUB-BANKING"]["status"] == "NEEDS_EVIDENCE"
    assert publications["PUB-KARMAGUIDE"]["status"] == "ANNOUNCED_NOT_CONFIRMED_PUBLISHED"
    assert publications["PUB-KARMAPOWER"]["status"] == "PUBLISHER_CATALOGUE_ENTRY"


def test_index_rejects_magic_and_universal_efficacy_claims() -> None:
    text = INDEX.read_text(encoding="utf-8")
    assert "не как независимое доказательство универсальных «законов судьбы»" in text
    assert "метафора «перепрошивки мозга»" in text
    assert "самогипноз заменяет диагностику" in text
