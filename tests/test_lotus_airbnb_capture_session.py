from __future__ import annotations

import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lotus_airbnb_capture_session.py"
SPEC = importlib.util.spec_from_file_location("lotus_airbnb_capture_session", SCRIPT)
assert SPEC and SPEC.loader
session = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(session)


def args(output_root: Path, *, acknowledge: bool = False) -> Namespace:
    """Build a minimal deterministic argument fixture for session tests."""
    return Namespace(
        profile=Path("profile.json"),
        capture_template=Path("template.json"),
        listing_url="https://www.airbnb.com/rooms/123",
        output_root=output_root,
        locale="en-US",
        timezone="Europe/Istanbul",
        ip_country="TR",
        authenticated=False,
        acknowledge_safe_scope=acknowledge,
    )


class LotusAirbnbCaptureSessionTests(unittest.TestCase):
    """Protect orchestration, attestation, isolation, and no-shell boundaries."""

    def test_plan_is_no_browser_and_uses_two_attempts(self) -> None:
        """The planning path must remain target-free and name two attempts."""
        with tempfile.TemporaryDirectory() as raw:
            value = session.plan(args(Path(raw) / "evidence"))
        self.assertFalse(value["target_interaction"])
        self.assertFalse(value["browser_imported"])
        self.assertFalse(value["shell_execution"])
        self.assertEqual(value["attempt_ids"], ["attempt-01", "attempt-02"])
        self.assertEqual(len(value["commands"]), 5)

    def test_runner_commands_are_argument_vectors_not_shell_strings(self) -> None:
        """Commands must be argv lists and carry the safe-scope acknowledgement."""
        command = session.runner_command(args(Path("out")), "attempt-01")
        self.assertIsInstance(command, list)
        self.assertIn("--acknowledge-safe-scope", command)
        self.assertNotIn("shell=True", command)

    def test_nonempty_output_is_rejected(self) -> None:
        """A session cannot mix new evidence with an existing output directory."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "old.txt").write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(session.SessionError, "absent or empty"):
                session.ensure_fresh_output(root)

    def test_screenshot_confirmation_requires_exact_token(self) -> None:
        """Finalization requires an exact post-capture human attestation."""
        with self.assertRaisesRegex(session.SessionError, "not explicitly attested"):
            session.confirm_screenshot_review(Path("out"), input_fn=lambda _: "yes")
        session.confirm_screenshot_review(
            Path("out"), input_fn=lambda _: session.SCREENSHOT_CONFIRMATION
        )

    def test_execute_requires_acknowledgement_and_tty(self) -> None:
        """Real sessions require both explicit scope acknowledgement and a TTY."""
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(session.SessionError, "acknowledge"):
                session.execute(
                    args(Path(raw) / "out"),
                    executor=lambda *a, **k: None,
                    stdin_isatty=lambda: True,
                )
            with self.assertRaisesRegex(session.SessionError, "interactive terminal"):
                session.execute(
                    args(Path(raw) / "out", acknowledge=True),
                    executor=lambda *a, **k: None,
                    stdin_isatty=lambda: False,
                )

    def test_execute_runs_plan_attempts_finalize_then_gate(self) -> None:
        """The wrapper must preserve the exact five-stage command ordering."""
        calls: list[list[str]] = []

        def executor(command, *, check):
            """Record a subprocess invocation without touching a browser or target."""
            self.assertTrue(check)
            calls.append(command)
            return None

        with tempfile.TemporaryDirectory() as raw:
            value = session.execute(
                args(Path(raw) / "out", acknowledge=True),
                executor=executor,
                input_fn=lambda _: session.SCREENSHOT_CONFIRMATION,
                stdin_isatty=lambda: True,
            )
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls[0][2], "plan")
        self.assertEqual(calls[1][2], "run")
        self.assertIn("attempt-01", calls[1])
        self.assertIn("attempt-02", calls[2])
        self.assertEqual(calls[3][2], "finalize")
        self.assertIn("lotus_capture_gate.py", calls[4][1])
        self.assertFalse(value["confirmed_defect"])


if __name__ == "__main__":
    unittest.main()
