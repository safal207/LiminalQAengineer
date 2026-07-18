#!/usr/bin/env python3
"""Validate a browser-capture packet before Lotus evidence review.

The gate validates evidence completeness and safety boundaries. It never promotes
an observation into a confirmed defect and never performs target interactions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_ARTIFACT_ROLES = {
    "screenshot_before",
    "screenshot_after",
    "network_archive",
    "state_before",
    "state_after",
    "transition_trace",
}
REQUIRED_ENV_FIELDS = {
    "browser",
    "browser_version",
    "device_timezone",
    "locale",
    "ip_country",
    "authenticated",
}


class CaptureError(ValueError):
    """Raised when a capture packet violates the evidence contract."""


class GateResult:
    """Immutable-style result object without external dependencies."""

    def __init__(
        self,
        *,
        status: str,
        evidence_grade: str,
        ready_for_review: bool,
        confirmed_defect: bool,
        reasons: tuple[str, ...],
    ) -> None:
        self.status = status
        self.evidence_grade = evidence_grade
        self.ready_for_review = ready_for_review
        self.confirmed_defect = confirmed_defect
        self.reasons = reasons

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence_grade": self.evidence_grade,
            "ready_for_review": self.ready_for_review,
            "confirmed_defect": self.confirmed_defect,
            "reasons": list(self.reasons),
        }


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise CaptureError(f"{path}: expected a JSON object")
    return value


def parse_ts(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CaptureError(f"{field}: invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CaptureError(f"{field}: timestamp must include a timezone")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("spec_version") != "lqa-lotus-capture/0.1":
        raise CaptureError("spec: unsupported spec_version")
    if spec.get("target") != "Airbnb":
        raise CaptureError("spec: this capture profile is scoped to Airbnb")
    if spec.get("stop_before") != "payment_submission":
        raise CaptureError("spec: stop_before must remain payment_submission")
    if spec.get("minimum_independent_attempts") != 2:
        raise CaptureError("spec: minimum_independent_attempts must equal 2")
    roles = set(spec.get("required_artifact_roles", []))
    if roles != REQUIRED_ARTIFACT_ROLES:
        raise CaptureError("spec: required artifact roles do not match the contract")


def _validate_artifact(artifact: dict[str, Any], root: Path) -> None:
    role = artifact.get("role")
    if role not in REQUIRED_ARTIFACT_ROLES:
        raise CaptureError(f"artifact: unsupported role {role!r}")
    relative = artifact.get("path")
    if not isinstance(relative, str) or not relative:
        raise CaptureError(f"artifact {role}: path is required")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise CaptureError(f"artifact {role}: path escapes capture root") from exc
    if not path.is_file():
        raise CaptureError(f"artifact {role}: missing file {relative}")
    expected = artifact.get("sha256")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise CaptureError(f"artifact {role}: sha256 must be 64 lowercase hex characters")
    actual = sha256_file(path)
    if actual != expected:
        raise CaptureError(f"artifact {role}: SHA mismatch")


def validate_capture(
    spec: dict[str, Any],
    capture: dict[str, Any],
    root: Path,
) -> GateResult:
    validate_spec(spec)

    if capture.get("capture_version") != "lqa-lotus-browser-capture/0.1":
        raise CaptureError("capture: unsupported capture_version")
    if capture.get("run_id") != "ABNB-RUN-002":
        raise CaptureError("capture: run_id must equal ABNB-RUN-002")
    if capture.get("target") != spec["target"]:
        raise CaptureError("capture: target must match capture spec")
    if capture.get("payment_submitted") is not False:
        raise CaptureError("capture: payment_submitted must remain false")
    if capture.get("reservation_created") is not False:
        raise CaptureError("capture: reservation_created must remain false")
    if capture.get("secrets_redacted") is not True:
        raise CaptureError("capture: secrets_redacted must be true")

    status = capture.get("status")
    if status == "planned":
        if capture.get("attempts") or capture.get("artifacts"):
            raise CaptureError("capture: planned template must not contain observed evidence")
        return GateResult(
            status="PLANNED",
            evidence_grade="F0",
            ready_for_review=False,
            confirmed_defect=False,
            reasons=("No browser execution evidence has been captured.",),
        )
    if status != "executed":
        raise CaptureError("capture: status must be planned or executed")

    environment = capture.get("environment")
    if not isinstance(environment, dict):
        raise CaptureError("capture: environment object is required")
    missing_env = sorted(REQUIRED_ENV_FIELDS - environment.keys())
    if missing_env:
        raise CaptureError(f"capture: missing environment fields: {missing_env}")

    started = parse_ts(capture.get("started_at"), "capture.started_at")
    completed = parse_ts(capture.get("completed_at"), "capture.completed_at")
    if completed < started:
        raise CaptureError("capture: completed_at precedes started_at")

    attempts = capture.get("attempts")
    if not isinstance(attempts, list) or len(attempts) < spec["minimum_independent_attempts"]:
        raise CaptureError("capture: at least two independent attempts are required")

    attempt_ids: set[str] = set()
    for attempt in attempts:
        attempt_id = attempt.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise CaptureError("capture: every attempt requires attempt_id")
        if attempt_id in attempt_ids:
            raise CaptureError("capture: attempt_id values must be unique")
        attempt_ids.add(attempt_id)
        if attempt.get("result") not in {"consistent", "inconsistent", "inconclusive"}:
            raise CaptureError(f"attempt {attempt_id}: invalid result")
        before = attempt.get("state_before")
        after = attempt.get("state_after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise CaptureError(f"attempt {attempt_id}: before/after states are required")
        for state_name, state in (("before", before), ("after", after)):
            for field in ("display_currency", "display_total", "captured_at"):
                if field not in state:
                    raise CaptureError(f"attempt {attempt_id}: {state_name}.{field} is required")
            parse_ts(state["captured_at"], f"attempt {attempt_id}.{state_name}.captured_at")

    artifacts = capture.get("artifacts")
    if not isinstance(artifacts, list):
        raise CaptureError("capture: artifacts must be a list")
    roles = [artifact.get("role") for artifact in artifacts]
    if set(roles) != REQUIRED_ARTIFACT_ROLES or len(roles) != len(REQUIRED_ARTIFACT_ROLES):
        raise CaptureError("capture: exactly one artifact for every required role is required")
    for artifact in artifacts:
        _validate_artifact(artifact, root)

    divergent_attempts = [a for a in attempts if a["result"] == "inconsistent"]
    if len(divergent_attempts) >= 2:
        grade = "F3"
        reason = "Two independent attempts recorded the same class of inconsistent state."
    else:
        grade = "F2"
        reason = "Executed browser evidence exists, but repeatable inconsistency is not established."

    return GateResult(
        status="READY_FOR_REVIEW",
        evidence_grade=grade,
        ready_for_review=True,
        confirmed_defect=False,
        reasons=(
            reason,
            "The gate validates completeness and integrity only.",
            "Pythia or a human reviewer must decide whether the evidence proves a defect.",
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        spec = load_json(args.spec)
        capture = load_json(args.capture)
        result = validate_capture(spec, capture, args.capture.parent)
    except (OSError, KeyError, TypeError, CaptureError) as exc:
        print(f"FAIL lotus capture gate: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
