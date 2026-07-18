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
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
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
        """Store one deterministic capture-gate outcome."""
        self.status = status
        self.evidence_grade = evidence_grade
        self.ready_for_review = ready_for_review
        self.confirmed_defect = confirmed_defect
        self.reasons = reasons

    def as_dict(self) -> dict[str, Any]:
        """Render the result as a JSON-serializable dictionary."""
        return {
            "status": self.status,
            "evidence_grade": self.evidence_grade,
            "ready_for_review": self.ready_for_review,
            "confirmed_defect": self.confirmed_defect,
            "reasons": list(self.reasons),
        }


def load_json(path: Path) -> dict[str, Any]:
    """Load one capture or profile JSON object from disk."""
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise CaptureError(f"{path}: expected a JSON object")
    return value


def parse_ts(value: Any, field: str) -> datetime:
    """Parse a required timezone-aware ISO-8601 timestamp for a named field."""
    if not isinstance(value, str) or not value:
        raise CaptureError(f"{field}: timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureError(f"{field}: invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CaptureError(f"{field}: timestamp must include a timezone")
    return parsed


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for one evidence artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_spec(spec: dict[str, Any]) -> None:
    """Validate the immutable Airbnb capture-profile safety contract."""
    if spec.get("spec_version") != "lqa-lotus-capture/0.1":
        raise CaptureError("spec: unsupported spec_version")
    if spec.get("profile_id") != "airbnb-currency-atomicity-v0.1":
        raise CaptureError("spec: unsupported profile_id")
    if spec.get("target") != "Airbnb":
        raise CaptureError("spec: this capture profile is scoped to Airbnb")
    if spec.get("stop_before") != "payment_submission":
        raise CaptureError("spec: stop_before must remain payment_submission")
    if spec.get("minimum_independent_attempts") != 2:
        raise CaptureError("spec: minimum_independent_attempts must equal 2")
    if set(spec.get("required_artifact_roles", [])) != REQUIRED_ARTIFACT_ROLES:
        raise CaptureError("spec: required artifact roles do not match the contract")


def validate_environment(environment: Any) -> dict[str, Any]:
    """Validate non-empty browser metadata and normalized locale/country/timezone values."""
    if not isinstance(environment, dict):
        raise CaptureError("capture: environment object is required")
    missing = sorted(REQUIRED_ENV_FIELDS - environment.keys())
    if missing:
        raise CaptureError(f"capture: missing environment fields: {missing}")
    for field in ("browser", "browser_version", "device_timezone", "locale", "ip_country"):
        if not isinstance(environment[field], str) or not environment[field].strip():
            raise CaptureError(f"capture: environment.{field} must be a non-empty string")
    if not isinstance(environment["authenticated"], bool):
        raise CaptureError("capture: environment.authenticated must be boolean")
    if not COUNTRY_RE.fullmatch(environment["ip_country"]):
        raise CaptureError("capture: environment.ip_country must be two uppercase letters")
    if not LOCALE_RE.fullmatch(environment["locale"]):
        raise CaptureError("capture: environment.locale has an invalid format")
    try:
        ZoneInfo(environment["device_timezone"])
    except ZoneInfoNotFoundError as exc:
        raise CaptureError("capture: environment.device_timezone is not a known timezone") from exc
    return environment


def _validate_artifact(artifact: dict[str, Any], root: Path) -> None:
    """Verify one artifact role, safe relative path, existence, and digest."""
    role = artifact.get("role")
    if role not in REQUIRED_ARTIFACT_ROLES:
        raise CaptureError(f"artifact: unsupported role {role!r}")
    relative = artifact.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise CaptureError(f"artifact {role}: path must be a non-empty relative path")
    resolved_root = root.resolve()
    path = (resolved_root / relative).resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise CaptureError(f"artifact {role}: path escapes capture root") from exc
    if not path.is_file():
        raise CaptureError(f"artifact {role}: missing file {relative}")
    expected = artifact.get("sha256")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise CaptureError(f"artifact {role}: sha256 must be 64 lowercase hex characters")
    if sha256_file(path) != expected:
        raise CaptureError(f"artifact {role}: SHA mismatch")


def validate_state(
    state: Any,
    *,
    attempt_id: str,
    state_name: str,
) -> tuple[dict[str, Any], datetime]:
    """Validate one visible-state snapshot and return its parsed timestamp."""
    if not isinstance(state, dict):
        raise CaptureError(f"attempt {attempt_id}: {state_name} state is required")
    for field in ("display_currency", "display_total", "captured_at"):
        if field not in state:
            raise CaptureError(f"attempt {attempt_id}: {state_name}.{field} is required")
    currency = state["display_currency"]
    total = state["display_total"]
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise CaptureError(
            f"attempt {attempt_id}: {state_name}.display_currency "
            "must be three uppercase letters"
        )
    if not isinstance(total, str) or not total.strip():
        raise CaptureError(
            f"attempt {attempt_id}: {state_name}.display_total "
            "must be a non-empty string"
        )
    return state, parse_ts(
        state["captured_at"],
        f"attempt {attempt_id}.{state_name}.captured_at",
    )


def inconsistency_fingerprint(attempt: dict[str, Any]) -> str:
    """Normalize an inconsistent attempt into a comparable transition class."""
    before = attempt["state_before"]
    after = attempt["state_after"]

    def normalize_total(value: str) -> str:
        """Remove whitespace and case differences from a visible total."""
        return re.sub(r"\s+", "", value).casefold()

    value = {
        "before_currency": before["display_currency"],
        "after_currency": after["display_currency"],
        "currency_changed": before["display_currency"] != after["display_currency"],
        "total_relation": (
            "unchanged"
            if normalize_total(before["display_total"])
            == normalize_total(after["display_total"])
            else "changed"
        ),
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate_capture(
    spec: dict[str, Any],
    capture: dict[str, Any],
    root: Path,
) -> GateResult:
    """Validate capture completeness and classify it without confirming a defect."""
    validate_spec(spec)
    if capture.get("capture_version") != "lqa-lotus-browser-capture/0.1":
        raise CaptureError("capture: unsupported capture_version")
    if capture.get("run_id") != "ABNB-RUN-002":
        raise CaptureError("capture: run_id must equal ABNB-RUN-002")
    if capture.get("target") != spec["target"]:
        raise CaptureError("capture: target must match capture spec")
    if capture.get("profile_id") != spec.get("profile_id"):
        raise CaptureError("capture: profile_id must match capture spec")
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

    validate_environment(capture.get("environment"))
    started = parse_ts(capture.get("started_at"), "capture.started_at")
    completed = parse_ts(capture.get("completed_at"), "capture.completed_at")
    if completed < started:
        raise CaptureError("capture: completed_at precedes started_at")

    attempts = capture.get("attempts")
    if not isinstance(attempts, list) or len(attempts) < spec["minimum_independent_attempts"]:
        raise CaptureError("capture: at least two independent attempts are required")

    attempt_ids: set[str] = set()
    context_ids: set[str] = set()
    inconsistent_fingerprints: list[str] = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise CaptureError("capture: every attempt must be an object")
        attempt_id = attempt.get("attempt_id")
        context_id = attempt.get("context_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise CaptureError("capture: every attempt requires attempt_id")
        if attempt_id in attempt_ids:
            raise CaptureError("capture: attempt_id values must be unique")
        attempt_ids.add(attempt_id)
        if not isinstance(context_id, str) or not context_id:
            raise CaptureError(f"attempt {attempt_id}: context_id is required")
        if context_id in context_ids:
            raise CaptureError("capture: context_id values must be unique")
        context_ids.add(context_id)
        result = attempt.get("result")
        if result not in {"consistent", "inconsistent", "inconclusive"}:
            raise CaptureError(f"attempt {attempt_id}: invalid result")
        before, before_ts = validate_state(
            attempt.get("state_before"),
            attempt_id=attempt_id,
            state_name="before",
        )
        after, after_ts = validate_state(
            attempt.get("state_after"),
            attempt_id=attempt_id,
            state_name="after",
        )
        if not (started <= before_ts <= after_ts <= completed):
            raise CaptureError(
                f"attempt {attempt_id}: timestamps must satisfy "
                "started_at <= before <= after <= completed_at"
            )
        attempt["state_before"] = before
        attempt["state_after"] = after
        if result == "inconsistent":
            inconsistent_fingerprints.append(inconsistency_fingerprint(attempt))

    artifacts = capture.get("artifacts")
    if not isinstance(artifacts, list):
        raise CaptureError("capture: artifacts must be a list")
    roles = [artifact.get("role") for artifact in artifacts]
    if set(roles) != REQUIRED_ARTIFACT_ROLES or len(roles) != len(REQUIRED_ARTIFACT_ROLES):
        raise CaptureError("capture: exactly one artifact for every required role is required")
    for artifact in artifacts:
        _validate_artifact(artifact, root)

    matching_reproduction = any(
        count >= 2 for count in Counter(inconsistent_fingerprints).values()
    )
    if matching_reproduction:
        grade = "F3"
        reason = (
            "Two independent browser contexts reproduced the same normalized "
            "inconsistency."
        )
    else:
        grade = "F2"
        reason = (
            "Executed browser evidence exists, but matching independent "
            "reproduction is not established."
        )
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
    """Run the capture gate and return a shell-friendly process status."""
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
