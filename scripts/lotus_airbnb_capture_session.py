#!/usr/bin/env python3
"""Orchestrate two operator-guided Airbnb captures and the Lotus evidence gate.

This wrapper adds no browser automation. It calls the existing headed Playwright
runner twice with separate attempt IDs, asks the operator to attest that generated
screenshots were reviewed for personal data, finalizes the bundle, and invokes the
capture gate. The ``plan`` command only prints the exact command sequence and never
imports Playwright or contacts Airbnb.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json"
DEFAULT_TEMPLATE = ROOT / "integrations/lotus/examples/airbnb-run-002.capture.json"
RUNNER = ROOT / "scripts/lotus_playwright_capture.py"
GATE = ROOT / "scripts/lotus_capture_gate.py"
ATTEMPT_IDS = ("attempt-01", "attempt-02")
SCREENSHOT_CONFIRMATION = "REVIEWED"


class SessionError(ValueError):
    """Raised when the session wrapper's safety or lifecycle contract is violated."""


def runner_command(args: argparse.Namespace, attempt_id: str) -> list[str]:
    """Build one headed, operator-guided runner command without invoking a shell."""
    command = [
        sys.executable,
        str(RUNNER),
        "run",
        "--profile",
        str(args.profile),
        "--capture-template",
        str(args.capture_template),
        "--listing-url",
        args.listing_url,
        "--attempt-id",
        attempt_id,
        "--output-root",
        str(args.output_root),
        "--locale",
        args.locale,
        "--timezone",
        args.timezone,
        "--ip-country",
        args.ip_country,
        "--acknowledge-safe-scope",
    ]
    if args.authenticated:
        command.append("--authenticated")
    return command


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    """Return the exact plan, two attempts, finalize, and gate command sequence."""
    common = [
        "--profile",
        str(args.profile),
        "--capture-template",
        str(args.capture_template),
    ]
    return [
        [sys.executable, str(RUNNER), "plan", *common],
        *(runner_command(args, attempt_id) for attempt_id in ATTEMPT_IDS),
        [
            sys.executable,
            str(RUNNER),
            "finalize",
            *common,
            "--output-root",
            str(args.output_root),
            "--confirm-screenshots-reviewed",
        ],
        [
            sys.executable,
            str(GATE),
            "--spec",
            str(args.profile),
            "--capture",
            str(args.output_root / "capture.json"),
        ],
    ]


def plan(args: argparse.Namespace) -> dict[str, Any]:
    """Print a no-browser execution plan suitable for CI and human review."""
    commands = build_commands(args)
    value = {
        "mode": "plan",
        "target_interaction": False,
        "browser_imported": False,
        "shell_execution": False,
        "attempt_ids": list(ATTEMPT_IDS),
        "output_root": str(args.output_root),
        "commands": commands,
        "confirmed_defect": False,
    }
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return value


def ensure_fresh_output(root: Path) -> None:
    """Reject a non-empty output directory so evidence from runs cannot be mixed."""
    if root.exists() and any(root.iterdir()):
        raise SessionError(f"output root must be absent or empty: {root}")
    root.mkdir(parents=True, exist_ok=True)


def confirm_screenshot_review(
    output_root: Path,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Require an explicit operator attestation after screenshots have been captured."""
    prompt = (
        f"\nReview every PNG under {output_root / 'attempts'} for personal data. "
        f"Type {SCREENSHOT_CONFIRMATION} to continue: "
    )
    if input_fn(prompt).strip() != SCREENSHOT_CONFIRMATION:
        raise SessionError("screenshot review was not explicitly attested")


def execute(
    args: argparse.Namespace,
    *,
    executor: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    input_fn: Callable[[str], str] = input,
    stdin_isatty: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run the bounded two-attempt session and stop if any contract command fails."""
    isatty = stdin_isatty or sys.stdin.isatty
    if not args.acknowledge_safe_scope:
        raise SessionError("--acknowledge-safe-scope is required")
    if not isatty():
        raise SessionError("capture session requires an interactive terminal")
    ensure_fresh_output(args.output_root)

    commands = build_commands(args)
    executor(commands[0], check=True)
    executor(commands[1], check=True)
    executor(commands[2], check=True)
    confirm_screenshot_review(args.output_root, input_fn=input_fn)
    executor(commands[3], check=True)
    executor(commands[4], check=True)

    value = {
        "status": "CAPTURE_GATE_COMPLETED",
        "attempt_ids": list(ATTEMPT_IDS),
        "capture": str(args.output_root / "capture.json"),
        "manifest": str(args.output_root / "evidence-manifest.json"),
        "confirmed_defect": False,
    }
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return value


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared paths and environment declarations to a subcommand parser."""
    parser.add_argument("--listing-url", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--capture-template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--timezone", default="Europe/Istanbul")
    parser.add_argument("--ip-country", default="TR")
    parser.add_argument("--authenticated", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line parser without importing browser dependencies."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    add_common_arguments(plan_parser)
    plan_parser.set_defaults(func=plan)

    run_parser = subparsers.add_parser("run")
    add_common_arguments(run_parser)
    run_parser.add_argument("--acknowledge-safe-scope", action="store_true")
    run_parser.set_defaults(func=execute)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the selected command and render contract failures as a non-zero exit."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (OSError, subprocess.CalledProcessError, SessionError) as exc:
        print(f"FAIL Lotus Airbnb capture session: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
