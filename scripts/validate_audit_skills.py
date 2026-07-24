#!/usr/bin/env python3
"""Validate the causal deep-audit skill family without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

SKILLS = {
    "causal-deep-audit": ROOT / "skills/causal-deep-audit/SKILL.md",
    "evidence-capture": ROOT / "skills/evidence-capture/SKILL.md",
    "causal-adjudication": ROOT / "skills/causal-adjudication/SKILL.md",
    "exact-head-governance": ROOT / "skills/exact-head-governance/SKILL.md",
    "logo-fidelity-transfer": ROOT / "skills/logo-fidelity-transfer/SKILL.md",
    "replay-memory": ROOT / "skills/replay-memory/SKILL.md",
    "product-impact": ROOT / "skills/product-impact/SKILL.md",
    "transition-next-action": ROOT / "skills/transition-next-action/SKILL.md",
}

SCHEMA = ROOT / "schemas/causal-deep-audit-packet.schema.json"
LOGO_EXAMPLE = ROOT / "skills/logo-fidelity-transfer/example.config.json"

REQUIRED_GLOBAL_TERMS = (
    "authority",
    "evidence",
)

SPECIALIZED_REQUIRED_TERMS = {
    "logo-fidelity-transfer": (
        "playwright",
        "pixelmatch",
        "reference",
        "selector",
        "aspect ratio",
        "human",
    ),
}

FORBIDDEN_AUTHORITY_CLAIMS = (
    "the audit may merge",
    "the audit may deploy",
    "the audit may contact external parties",
    "missing evidence is success",
)


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing opening frontmatter delimiter")
    try:
        _, raw, body = text.split("---\n", 2)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc

    data: dict[str, str] = {}
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {raw_line!r}")
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data, body


def validate_skill_text(expected_name: str, text: str) -> list[str]:
    errors: list[str] = []
    try:
        metadata, body = _frontmatter(text)
    except ValueError as exc:
        return [str(exc)]

    if metadata.get("name") != expected_name:
        errors.append(
            f"frontmatter name must be {expected_name!r}, got {metadata.get('name')!r}"
        )
    if len(metadata.get("description", "")) < 40:
        errors.append("description must explain the trigger and purpose")
    if len(body.strip()) < 500:
        errors.append("skill body is too small to define an auditable workflow")

    lowered = body.lower()
    for term in REQUIRED_GLOBAL_TERMS:
        if term not in lowered:
            errors.append(f"required global term missing: {term}")
    for term in SPECIALIZED_REQUIRED_TERMS.get(expected_name, ()):
        if term not in lowered:
            errors.append(f"specialized required term missing: {term}")
    for claim in FORBIDDEN_AUTHORITY_CLAIMS:
        if claim in lowered:
            errors.append(f"forbidden authority claim present: {claim}")

    if not re.search(r"\b(not_run|needs_evidence|incomplete|blocked|hold)\b", lowered):
        errors.append("skill must preserve at least one explicit uncertainty/fail-closed state")

    return errors


def validate_logo_example(config: dict) -> list[str]:
    errors: list[str] = []
    if config.get("schema_version") != "logo-fidelity-transfer-v0.1":
        errors.append("logo example schema_version must be logo-fidelity-transfer-v0.1")

    comparison = config.get("comparison") or {}
    if comparison.get("engine") != "pixelmatch":
        errors.append("logo comparison engine must be pixelmatch")
    threshold = comparison.get("threshold")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        errors.append("logo comparison threshold must be between 0 and 1")
    if comparison.get("structural_mismatch_always_blocks") is not True:
        errors.append("structural logo mismatch must fail closed")

    target = config.get("target") or {}
    for field in ("repository_full_name", "source_sha", "route", "selector"):
        if not target.get(field):
            errors.append(f"logo target missing required field: {field}")

    profiles = config.get("profiles") or []
    profile_ids = {item.get("id") for item in profiles if isinstance(item, dict)}
    if not {"desktop-chromium", "mobile-chromium"}.issubset(profile_ids):
        errors.append("logo example must include desktop and mobile Chromium profiles")

    authority = config.get("authority") or {}
    for field in (
        "reference_use_confirmed",
        "repository_write_authorized",
        "deployment_authorized",
        "merge_authorized",
    ):
        if authority.get(field) is not False:
            errors.append(f"logo example authority must default {field} to false")

    if not config.get("stop_conditions"):
        errors.append("logo example must define stop conditions")
    return errors


def validate_schema(schema: dict) -> list[str]:
    errors: list[str] = []
    required = set(schema.get("required", []))
    for field in ("source_identity", "authority", "verdict", "evidence_ledger", "next_action"):
        if field not in required:
            errors.append(f"schema missing required top-level field: {field}")

    try:
        states = set(
            schema["properties"]["verdict"]["properties"]["state"]["enum"]
        )
        evidence_states = set(
            schema["$defs"]["evidence"]["properties"]["status"]["enum"]
        )
        gates = set(
            schema["properties"]["verdict"]["properties"]["gate"]["enum"]
        )
    except (KeyError, TypeError) as exc:
        errors.append(f"schema verdict/evidence structure is incomplete: {exc}")
        return errors

    for state in ("NOT_RUN", "NEEDS_EVIDENCE", "INCOMPLETE", "HOLD"):
        if state not in states:
            errors.append(f"schema verdict states missing fail-closed value: {state}")
    for state in ("NOT_RUN", "UNAVAILABLE", "STALE", "INCOMPLETE"):
        if state not in evidence_states:
            errors.append(f"schema evidence states missing value: {state}")
    if gates != {"ALLOW_REPORT", "ESCALATE", "BLOCK"}:
        errors.append("schema gate enum must be exactly ALLOW_REPORT/ESCALATE/BLOCK")

    return errors


def validate_repository() -> list[str]:
    errors: list[str] = []

    for name, path in SKILLS.items():
        if not path.is_file():
            errors.append(f"missing skill file: {path.relative_to(ROOT)}")
            continue
        for error in validate_skill_text(name, path.read_text(encoding="utf-8")):
            errors.append(f"{path.relative_to(ROOT)}: {error}")

    if not SCHEMA.is_file():
        errors.append(f"missing schema: {SCHEMA.relative_to(ROOT)}")
    else:
        try:
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid schema JSON: {exc}")
        else:
            errors.extend(f"schema: {error}" for error in validate_schema(schema))

    if not LOGO_EXAMPLE.is_file():
        errors.append(f"missing logo example: {LOGO_EXAMPLE.relative_to(ROOT)}")
    else:
        try:
            config = json.loads(LOGO_EXAMPLE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid logo example JSON: {exc}")
        else:
            errors.extend(
                f"logo example: {error}" for error in validate_logo_example(config)
            )

    orchestrator = SKILLS["causal-deep-audit"]
    if orchestrator.is_file():
        text = orchestrator.read_text(encoding="utf-8")
        for dependency in SKILLS:
            if dependency == "causal-deep-audit":
                continue
            if dependency not in text:
                errors.append(f"orchestrator does not invoke dependency: {dependency}")

    return errors


def main(argv: Iterable[str] | None = None) -> int:
    del argv
    errors = validate_repository()
    if errors:
        print("Audit skill contract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(SKILLS)} causal deep-audit skills and packet schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
