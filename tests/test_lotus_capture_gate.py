import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/lotus_capture_gate.py"
SPEC = importlib.util.spec_from_file_location("lotus_capture_gate", MODULE_PATH)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

SPEC_PATH = ROOT / "integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json"
TEMPLATE_PATH = ROOT / "integrations/lotus/examples/airbnb-run-002.capture.json"


def digest(path: Path) -> str:
    """Return the SHA-256 digest used by fixture artifact metadata."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LotusCaptureGateTests(unittest.TestCase):
    """Protect evidence promotion, integrity, and non-destructive boundaries."""

    def setUp(self) -> None:
        """Load clean profile and capture-template fixtures for every test."""
        self.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        self.template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_planned_template_stays_f0_and_unconfirmed(self) -> None:
        """An unexecuted template must remain F0 and unconfirmed."""
        result = gate.validate_capture(self.spec, self.template, TEMPLATE_PATH.parent)
        self.assertEqual(result.status, "PLANNED")
        self.assertEqual(result.evidence_grade, "F0")
        self.assertFalse(result.ready_for_review)
        self.assertFalse(result.confirmed_defect)

    def test_payment_submission_is_rejected(self) -> None:
        """Any claimed payment submission must fail the safety contract."""
        invalid = copy.deepcopy(self.template)
        invalid["payment_submitted"] = True
        with self.assertRaisesRegex(gate.CaptureError, "payment_submitted"):
            gate.validate_capture(self.spec, invalid, TEMPLATE_PATH.parent)

    def test_reservation_creation_is_rejected(self) -> None:
        """Any claimed reservation creation must fail the safety contract."""
        invalid = copy.deepcopy(self.template)
        invalid["reservation_created"] = True
        with self.assertRaisesRegex(gate.CaptureError, "reservation_created"):
            gate.validate_capture(self.spec, invalid, TEMPLATE_PATH.parent)

    def test_profile_mismatch_is_rejected(self) -> None:
        """A capture cannot silently switch to another profile contract."""
        invalid = copy.deepcopy(self.template)
        invalid["profile_id"] = "other-profile"
        with self.assertRaisesRegex(gate.CaptureError, "profile_id"):
            gate.validate_capture(self.spec, invalid, TEMPLATE_PATH.parent)

    def test_executed_capture_requires_two_attempts(self) -> None:
        """One executed attempt cannot satisfy independent reproduction."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"] = capture["attempts"][:1]
            with self.assertRaisesRegex(gate.CaptureError, "two independent attempts"):
                gate.validate_capture(self.spec, capture, root)

    def test_complete_repeated_capture_is_ready_but_not_confirmed(self) -> None:
        """Two matching contexts may reach F3 but cannot confirm a defect."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            result = gate.validate_capture(self.spec, capture, root)
            self.assertEqual(result.status, "READY_FOR_REVIEW")
            self.assertEqual(result.evidence_grade, "F3")
            self.assertTrue(result.ready_for_review)
            self.assertFalse(result.confirmed_defect)

    def test_authenticated_capture_is_rejected(self) -> None:
        """The public capture profile must reject authenticated evidence."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["environment"]["authenticated"] = True
            with self.assertRaisesRegex(gate.CaptureError, "must remain false"):
                gate.validate_capture(self.spec, capture, root)

    def test_reused_context_is_rejected(self) -> None:
        """Two attempt IDs cannot reuse one browser context."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"][1]["context_id"] = capture["attempts"][0]["context_id"]
            with self.assertRaisesRegex(gate.CaptureError, "context_id values must be unique"):
                gate.validate_capture(self.spec, capture, root)

    def test_mismatched_fingerprints_stay_f2(self) -> None:
        """Different derived inconsistency classes cannot become one reproduction."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"][1]["state_after"]["display_currency"] = "TRY"
            capture["attempts"][1]["state_after"]["display_total"] = "19000"
            self._rewrite_state_bundles(root, capture)
            result = gate.validate_capture(self.spec, capture, root)
            self.assertEqual(result.evidence_grade, "F2")
            self.assertFalse(result.confirmed_defect)

    def test_self_declared_inconsistency_requires_visible_state_support(self) -> None:
        """A declaration alone cannot promote an attempt toward F3."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"][0]["state_after"]["display_total"] = "19000"
            self._rewrite_state_bundles(root, capture)
            with self.assertRaisesRegex(gate.CaptureError, "not supported by visible state"):
                gate.validate_capture(self.spec, capture, root)

    def test_non_string_timestamp_is_rejected(self) -> None:
        """Missing or non-string timestamps must become contract errors."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["started_at"] = None
            with self.assertRaisesRegex(gate.CaptureError, "timestamp is required"):
                gate.validate_capture(self.spec, capture, root)

    def test_invalid_environment_values_are_rejected(self) -> None:
        """Empty metadata and non-boolean authentication are invalid."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["environment"]["browser"] = ""
            with self.assertRaisesRegex(gate.CaptureError, "environment.browser"):
                gate.validate_capture(self.spec, capture, root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["environment"]["authenticated"] = "false"
            with self.assertRaisesRegex(gate.CaptureError, "authenticated"):
                gate.validate_capture(self.spec, capture, root)

    def test_state_timestamps_must_be_ordered_and_in_window(self) -> None:
        """State times must remain ordered inside the capture window."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"][0]["state_before"]["captured_at"] = (
                "2026-07-19T10:00:20+03:00"
            )
            capture["attempts"][0]["state_after"]["captured_at"] = (
                "2026-07-19T10:00:10+03:00"
            )
            with self.assertRaisesRegex(gate.CaptureError, "started_at <= before <= after"):
                gate.validate_capture(self.spec, capture, root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["attempts"][0]["state_before"]["captured_at"] = (
                "2026-07-19T09:59:59+03:00"
            )
            with self.assertRaisesRegex(gate.CaptureError, "started_at <= before <= after"):
                gate.validate_capture(self.spec, capture, root)

    def test_sha_mismatch_is_rejected(self) -> None:
        """Artifact tampering must be detected before evidence review."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            capture["artifacts"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(gate.CaptureError, "SHA mismatch"):
                gate.validate_capture(self.spec, capture, root)

    def test_missing_attempt_zip_member_is_rejected(self) -> None:
        """A shared bundle cannot stand in for missing per-attempt evidence."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            before_zip = root / "screenshots-before.zip"
            with zipfile.ZipFile(before_zip, "w") as archive:
                archive.writestr("attempt-1/before.png", b"only-one-attempt")
            self._refresh_artifact_digest(capture, "screenshot_before", before_zip)
            with self.assertRaisesRegex(gate.CaptureError, "attempt members mismatch"):
                gate.validate_capture(self.spec, capture, root)

    def test_trace_context_must_bind_to_declared_attempt(self) -> None:
        """A unique context_id must also be present in that attempt's trace."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            trace_path = root / "transitions.ttrace.jsonl"
            records = [json.loads(line) for line in trace_path.read_text().splitlines()]
            records[0]["context_id"] = "other-context"
            trace_path.write_text(
                "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
                encoding="utf-8",
            )
            self._refresh_artifact_digest(capture, "transition_trace", trace_path)
            with self.assertRaisesRegex(gate.CaptureError, "trace context_id mismatch"):
                gate.validate_capture(self.spec, capture, root)

    def test_state_bundle_must_match_capture_attempt(self) -> None:
        """State JSON must bind the digest to the exact attempt-level state."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = self._executed_capture(root)
            state_path = root / "states-before.json"
            states = json.loads(state_path.read_text())
            states[0]["display_total"] = "tampered"
            state_path.write_text(json.dumps(states), encoding="utf-8")
            self._refresh_artifact_digest(capture, "state_before", state_path)
            with self.assertRaisesRegex(gate.CaptureError, "state_before artifact mismatch"):
                gate.validate_capture(self.spec, capture, root)

    def _refresh_artifact_digest(
        self, capture: dict, role: str, path: Path
    ) -> None:
        for artifact in capture["artifacts"]:
            if artifact["role"] == role:
                artifact["sha256"] = digest(path)
                return
        self.fail(f"missing artifact role {role}")

    def _rewrite_state_bundles(self, root: Path, capture: dict) -> None:
        before = [
            {"attempt_id": attempt["attempt_id"], **attempt["state_before"]}
            for attempt in capture["attempts"]
        ]
        after = [
            {"attempt_id": attempt["attempt_id"], **attempt["state_after"]}
            for attempt in capture["attempts"]
        ]
        before_path = root / "states-before.json"
        after_path = root / "states-after.json"
        before_path.write_text(json.dumps(before), encoding="utf-8")
        after_path.write_text(json.dumps(after), encoding="utf-8")
        self._refresh_artifact_digest(capture, "state_before", before_path)
        self._refresh_artifact_digest(capture, "state_after", after_path)

    def _executed_capture(self, root: Path) -> dict:
        """Create a complete two-context capture fixture with bound bundle members."""
        attempts = [
            {
                "attempt_id": "attempt-1",
                "context_id": "context-1",
                "result": "inconsistent",
                "state_before": {
                    "display_currency": "TRY",
                    "display_total": "18500",
                    "captured_at": "2026-07-19T10:00:00+03:00",
                },
                "state_after": {
                    "display_currency": "EUR",
                    "display_total": "18500",
                    "captured_at": "2026-07-19T10:00:05+03:00",
                },
            },
            {
                "attempt_id": "attempt-2",
                "context_id": "context-2",
                "result": "inconsistent",
                "state_before": {
                    "display_currency": "TRY",
                    "display_total": "18500",
                    "captured_at": "2026-07-19T10:05:00+03:00",
                },
                "state_after": {
                    "display_currency": "EUR",
                    "display_total": "18500",
                    "captured_at": "2026-07-19T10:05:05+03:00",
                },
            },
        ]

        before_zip = root / "screenshots-before.zip"
        after_zip = root / "screenshots-after.zip"
        network_zip = root / "network-archives.zip"
        with zipfile.ZipFile(before_zip, "w") as archive:
            for attempt in attempts:
                archive.writestr(
                    f"{attempt['attempt_id']}/before.png",
                    f"before-{attempt['attempt_id']}".encode(),
                )
        with zipfile.ZipFile(after_zip, "w") as archive:
            for attempt in attempts:
                archive.writestr(
                    f"{attempt['attempt_id']}/after_currency.png",
                    f"after-currency-{attempt['attempt_id']}".encode(),
                )
                archive.writestr(
                    f"{attempt['attempt_id']}/after_history.png",
                    f"after-history-{attempt['attempt_id']}".encode(),
                )
        with zipfile.ZipFile(network_zip, "w") as archive:
            for attempt in attempts:
                archive.writestr(
                    f"{attempt['attempt_id']}/network.har",
                    json.dumps({"attempt_id": attempt["attempt_id"]}),
                )

        before_states_path = root / "states-before.json"
        after_states_path = root / "states-after.json"
        before_states_path.write_text(
            json.dumps(
                [
                    {"attempt_id": attempt["attempt_id"], **attempt["state_before"]}
                    for attempt in attempts
                ]
            ),
            encoding="utf-8",
        )
        after_states_path.write_text(
            json.dumps(
                [
                    {"attempt_id": attempt["attempt_id"], **attempt["state_after"]}
                    for attempt in attempts
                ]
            ),
            encoding="utf-8",
        )

        trace_path = root / "transitions.ttrace.jsonl"
        trace_records = []
        for attempt in attempts:
            attempt_id = attempt["attempt_id"]
            trace_records.extend(
                [
                    {
                        "id": f"{attempt_id}-sense",
                        "type": "sense",
                        "attempt_id": attempt_id,
                        "context_id": attempt["context_id"],
                    },
                    {
                        "id": f"{attempt_id}-transition",
                        "type": "transition",
                        "attempt_id": attempt_id,
                    },
                    {
                        "id": f"{attempt_id}-commit",
                        "type": "commit",
                        "attempt_id": attempt_id,
                    },
                ]
            )
        trace_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in trace_records),
            encoding="utf-8",
        )

        artifacts = []
        for role, path in (
            ("screenshot_before", before_zip),
            ("screenshot_after", after_zip),
            ("network_archive", network_zip),
            ("state_before", before_states_path),
            ("state_after", after_states_path),
            ("transition_trace", trace_path),
        ):
            artifacts.append({"role": role, "path": path.name, "sha256": digest(path)})

        return {
            "capture_version": "lqa-lotus-browser-capture/0.1",
            "run_id": "ABNB-RUN-002",
            "target": "Airbnb",
            "profile_id": "airbnb-currency-atomicity-v0.1",
            "status": "executed",
            "payment_submitted": False,
            "reservation_created": False,
            "secrets_redacted": True,
            "started_at": "2026-07-19T10:00:00+03:00",
            "completed_at": "2026-07-19T10:06:00+03:00",
            "environment": {
                "browser": "Chromium",
                "browser_version": "fixture",
                "device_timezone": "Europe/Istanbul",
                "locale": "en-US",
                "ip_country": "TR",
                "authenticated": False,
            },
            "attempts": attempts,
            "artifacts": artifacts,
        }


if __name__ == "__main__":
    unittest.main()
