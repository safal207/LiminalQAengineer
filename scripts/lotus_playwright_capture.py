#!/usr/bin/env python3
"""Operator-guided Playwright capture for the LiminalQA × Lotus Airbnb audit.

The runner never automates clicks or form submission. It opens an allowlisted
public Airbnb URL in a fresh headed browser context, records operator-confirmed
checkpoints, aborts known payment/reservation submission requests, redacts
sensitive HAR fields, and packages artifacts for the Lotus capture gate.

Playwright is imported only by the ``run`` command. ``plan`` and ``finalize``
use the Python standard library and are safe to run in CI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

RUN_ID = "ABNB-RUN-002"
PROFILE_ID = "airbnb-currency-atomicity-v0.1"
CAPTURE_VERSION = "lqa-lotus-browser-capture/0.1"
ALLOWED_HOST_SUFFIXES = ("airbnb.com",)
ATTEMPT_SCHEMA = "lqa-lotus-playwright-attempt/0.1"
REQUIRED_CHECKPOINTS = ("before", "after_currency", "after_history")
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrf-token",
    "x-xsrf-token",
    "proxy-authorization",
}
DANGEROUS_REQUEST_RE = re.compile(
    r"/(?:payments?|reservations?)(?:/|$)|"
    r"/(?:book|booking|checkout)/(?:confirm|create|submit|complete)(?:/|$)",
    re.IGNORECASE,
)
MONEY_RE = re.compile(
    r"(?:(?:TRY|EUR|USD|GBP|PLN|CHF)\s?[\d.,]+|"
    r"[\d.,]+\s?(?:TRY|EUR|USD|GBP|PLN|CHF)|"
    r"[€$£₺]\s?[\d.,]+)",
    re.IGNORECASE,
)


class RunnerError(ValueError):
    """Raised when the capture runner's safety or evidence contract is violated."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RunnerError(f"{path}: expected a JSON object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("spec_version") != "lqa-lotus-capture/0.1":
        raise RunnerError("profile: unsupported spec_version")
    if profile.get("profile_id") != PROFILE_ID:
        raise RunnerError(f"profile: profile_id must equal {PROFILE_ID}")
    if profile.get("target") != "Airbnb":
        raise RunnerError("profile: target must remain Airbnb")
    if profile.get("stop_before") != "payment_submission":
        raise RunnerError("profile: stop_before must remain payment_submission")
    if profile.get("minimum_independent_attempts") != 2:
        raise RunnerError("profile: two independent attempts are required")


def validate_template(template: dict[str, Any]) -> None:
    if template.get("capture_version") != CAPTURE_VERSION:
        raise RunnerError("template: unsupported capture_version")
    if template.get("run_id") != RUN_ID:
        raise RunnerError(f"template: run_id must equal {RUN_ID}")
    if template.get("profile_id") != PROFILE_ID:
        raise RunnerError(f"template: profile_id must equal {PROFILE_ID}")
    if template.get("payment_submitted") is not False:
        raise RunnerError("template: payment_submitted must remain false")
    if template.get("reservation_created") is not False:
        raise RunnerError("template: reservation_created must remain false")


def validate_listing_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise RunnerError("listing URL must use https")
    if parsed.username or parsed.password:
        raise RunnerError("listing URL must not contain credentials")
    if parsed.port not in (None, 443):
        raise RunnerError("listing URL must use the default HTTPS port")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES):
        raise RunnerError("listing URL host is not allowlisted for Airbnb")
    return value


def is_dangerous_request(method: str, url: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and bool(
        DANGEROUS_REQUEST_RE.search(urlparse(url).path)
    )


def safe_child(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise RunnerError("artifact path must be a non-empty relative path")
    root_resolved = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise RunnerError(f"artifact path escapes output root: {relative}") from exc
    return candidate


def redact_json(value: Any, parent_key: str | None = None) -> tuple[Any, int]:
    """Recursively redact common HAR secret fields."""
    count = 0
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            lowered = key.lower()
            if lowered in {"cookies", "cookie", "postdata"}:
                if child not in (None, "", [], {}):
                    count += 1
                result[key] = "[REDACTED]"
                continue
            if (
                lowered == "value"
                and isinstance(value.get("name"), str)
                and value["name"].lower() in SENSITIVE_HEADER_NAMES
            ):
                if child not in (None, ""):
                    count += 1
                result[key] = "[REDACTED]"
                continue
            redacted, child_count = redact_json(child, lowered)
            result[key] = redacted
            count += child_count
        return result, count
    if isinstance(value, list):
        result_list = []
        for child in value:
            redacted, child_count = redact_json(child, parent_key)
            result_list.append(redacted)
            count += child_count
        return result_list, count
    return value, 0


def redact_har(raw_path: Path, redacted_path: Path) -> dict[str, Any]:
    if not raw_path.is_file():
        raise RunnerError(f"missing raw HAR: {raw_path}")
    value = json.loads(raw_path.read_text(encoding="utf-8"))
    redacted, count = redact_json(value)
    write_json(redacted_path, redacted)
    raw_path.unlink()
    return {
        "redacted_fields": count,
        "raw_deleted": True,
        "output": redacted_path.name,
        "sha256": sha256_file(redacted_path),
    }


def money_samples(text: str, limit: int = 20) -> list[str]:
    samples: list[str] = []
    for match in MONEY_RE.finditer(text):
        value = match.group(0).strip()
        if value not in samples:
            samples.append(value)
        if len(samples) >= limit:
            break
    return samples


def operator_value(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("A non-empty value is required.", file=sys.stderr)


def checkpoint(page: Any, attempt_dir: Path, name: str) -> dict[str, Any]:
    if name not in REQUIRED_CHECKPOINTS:
        raise RunnerError(f"unsupported checkpoint: {name}")
    input(f"\nPrepare checkpoint '{name}' in the visible browser, then press Enter...")
    display_currency = operator_value("Visible currency code (for example TRY/EUR/USD)")
    display_total = operator_value("Visible total exactly as shown")
    body_text = page.locator("body").inner_text(timeout=10_000)
    state = {
        "checkpoint": name,
        "captured_at": utc_now(),
        "url": page.url,
        "title": page.title(),
        "display_currency": display_currency,
        "display_total": display_total,
        "visible_money_samples": money_samples(body_text),
    }
    screenshot = attempt_dir / f"{name}.png"
    state_path = attempt_dir / f"{name}.state.json"
    page.screenshot(path=str(screenshot), full_page=True)
    write_json(state_path, state)
    return {
        "state": state,
        "state_path": state_path.name,
        "state_sha256": sha256_file(state_path),
        "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256_file(screenshot),
    }


def build_trace(
    attempt_id: str,
    context_id: str,
    started_at: str,
    completed_at: str,
    result: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{attempt_id}-sense",
            "type": "sense",
            "ts": started_at,
            "thread_id": RUN_ID,
            "attempt_id": attempt_id,
            "context_id": context_id,
            "input": "operator-guided public Airbnb currency-state capture started",
        },
        {
            "id": f"{attempt_id}-transition",
            "type": "transition",
            "ts": completed_at,
            "thread_id": RUN_ID,
            "attempt_id": attempt_id,
            "from": "before",
            "to": "after_currency_then_history_restore",
        },
        {
            "id": f"{attempt_id}-commit",
            "type": "commit",
            "ts": completed_at,
            "thread_id": RUN_ID,
            "attempt_id": attempt_id,
            "result": result,
            "confirmed_defect": False,
        },
    ]


def execute_attempt(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_json(args.profile)
    template = load_json(args.capture_template)
    validate_profile(profile)
    validate_template(template)
    listing_url = validate_listing_url(args.listing_url)
    if not args.acknowledge_safe_scope:
        raise RunnerError("--acknowledge-safe-scope is required for a browser run")
    if not sys.stdin.isatty():
        raise RunnerError("browser capture requires an interactive terminal")

    attempt_root = args.output_root / "attempts"
    attempt_dir = safe_child(attempt_root, args.attempt_id)
    if attempt_dir.exists():
        raise RunnerError(f"attempt directory already exists: {attempt_dir}")
    attempt_dir.mkdir(parents=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RunnerError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    started_at = utc_now()
    context_id = str(uuid.uuid4())
    blocked_requests: list[dict[str, str]] = []
    raw_har = attempt_dir / "network.raw.har"
    redacted_har = attempt_dir / "network.har"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(
            locale=args.locale,
            timezone_id=args.timezone,
            record_har_path=str(raw_har),
            record_har_mode="minimal",
        )

        def route_handler(route: Any, request: Any) -> None:
            if is_dangerous_request(request.method, request.url):
                blocked_requests.append(
                    {"method": request.method, "url": request.url, "captured_at": utc_now()}
                )
                route.abort()
            else:
                route.continue_()

        context.route("**/*", route_handler)
        page = context.new_page()
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60_000)

        print(
            "\nThe runner performs no clicks. In the visible browser:"
            "\n1. Select dates and one guest, keep the initial currency."
            "\n2. Capture 'before'."
            "\n3. Change currency manually and capture 'after_currency'."
            "\n4. Use Back then Forward and capture 'after_history'."
            "\nDo not submit payment or create a reservation."
        )
        checkpoints = {
            name: checkpoint(page, attempt_dir, name) for name in REQUIRED_CHECKPOINTS
        }
        result = operator_value("Result: consistent / inconsistent / inconclusive").lower()
        if result not in {"consistent", "inconsistent", "inconclusive"}:
            raise RunnerError("result must be consistent, inconsistent, or inconclusive")

        browser_version = browser.version
        context.close()
        browser.close()

    har_report = redact_har(raw_har, redacted_har)
    completed_at = utc_now()
    trace = build_trace(args.attempt_id, context_id, started_at, completed_at, result)
    trace_path = attempt_dir / "transitions.ttrace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in trace),
        encoding="utf-8",
    )
    blocked_path = attempt_dir / "blocked-requests.json"
    write_json(blocked_path, blocked_requests)

    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "run_id": RUN_ID,
        "profile_id": PROFILE_ID,
        "attempt_id": args.attempt_id,
        "context_id": context_id,
        "listing_url": listing_url,
        "started_at": started_at,
        "completed_at": completed_at,
        "result": result,
        "environment": {
            "browser": "Chromium",
            "browser_version": browser_version,
            "device_timezone": args.timezone,
            "locale": args.locale,
            "ip_country": args.ip_country.upper(),
            "authenticated": bool(args.authenticated),
        },
        "safety": {
            "operator_guided": True,
            "automated_clicks": False,
            "payment_submitted": False,
            "reservation_created": False,
            "blocked_request_count": len(blocked_requests),
        },
        "redaction": {
            "har": har_report,
            "screenshots_reviewed": False,
            "note": "Human screenshot review is required during finalize.",
        },
        "checkpoints": checkpoints,
        "artifacts": {
            "network_archive": {
                "path": redacted_har.name,
                "sha256": sha256_file(redacted_har),
            },
            "transition_trace": {
                "path": trace_path.name,
                "sha256": sha256_file(trace_path),
            },
            "blocked_requests": {
                "path": blocked_path.name,
                "sha256": sha256_file(blocked_path),
            },
        },
    }
    write_json(attempt_dir / "attempt.json", attempt)
    print(json.dumps({"attempt": str(attempt_dir), "result": result}, indent=2))
    return attempt


def load_attempt(path: Path) -> dict[str, Any]:
    attempt_path = path / "attempt.json"
    attempt = load_json(attempt_path)
    if attempt.get("schema_version") != ATTEMPT_SCHEMA:
        raise RunnerError(f"{attempt_path}: unsupported attempt schema")
    if attempt.get("run_id") != RUN_ID or attempt.get("profile_id") != PROFILE_ID:
        raise RunnerError(f"{attempt_path}: run/profile mismatch")
    if attempt.get("safety", {}).get("payment_submitted") is not False:
        raise RunnerError(f"{attempt_path}: payment_submitted must remain false")
    if attempt.get("safety", {}).get("reservation_created") is not False:
        raise RunnerError(f"{attempt_path}: reservation_created must remain false")
    for name in REQUIRED_CHECKPOINTS:
        checkpoint_value = attempt.get("checkpoints", {}).get(name)
        if not isinstance(checkpoint_value, dict):
            raise RunnerError(f"{attempt_path}: missing checkpoint {name}")
        for field in ("state_path", "state_sha256", "screenshot_path", "screenshot_sha256"):
            if not checkpoint_value.get(field):
                raise RunnerError(f"{attempt_path}: checkpoint {name} missing {field}")
        for path_field, hash_field in (
            ("state_path", "state_sha256"),
            ("screenshot_path", "screenshot_sha256"),
        ):
            artifact = safe_child(path, checkpoint_value[path_field])
            if not artifact.is_file() or sha256_file(artifact) != checkpoint_value[hash_field]:
                raise RunnerError(f"{attempt_path}: checkpoint {name} integrity failure")
    for role in ("network_archive", "transition_trace"):
        artifact_meta = attempt.get("artifacts", {}).get(role)
        if not isinstance(artifact_meta, dict):
            raise RunnerError(f"{attempt_path}: missing {role}")
        artifact = safe_child(path, artifact_meta["path"])
        if not artifact.is_file() or sha256_file(artifact) != artifact_meta["sha256"]:
            raise RunnerError(f"{attempt_path}: {role} integrity failure")
    return attempt


def zip_files(output: Path, members: Iterable[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, arcname in members:
            archive.write(source, arcname=arcname)


def final_artifact(role: str, path: Path, root: Path) -> dict[str, str]:
    return {
        "role": role,
        "path": str(path.relative_to(root)),
        "sha256": sha256_file(path),
    }


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_json(args.profile)
    template = load_json(args.capture_template)
    validate_profile(profile)
    validate_template(template)
    if not args.confirm_screenshots_reviewed:
        raise RunnerError(
            "--confirm-screenshots-reviewed is required; the runner cannot inspect screenshots for personal data"
        )

    attempts_root = args.output_root / "attempts"
    if not attempts_root.is_dir():
        raise RunnerError("no attempts directory found")
    attempt_dirs = sorted(path for path in attempts_root.iterdir() if path.is_dir())
    if len(attempt_dirs) < profile["minimum_independent_attempts"]:
        raise RunnerError("at least two independent attempt directories are required")

    attempts = [load_attempt(path) for path in attempt_dirs]
    attempt_ids = [attempt["attempt_id"] for attempt in attempts]
    context_ids = [attempt["context_id"] for attempt in attempts]
    if len(set(attempt_ids)) != len(attempt_ids):
        raise RunnerError("attempt_id values must be unique")
    if len(set(context_ids)) != len(context_ids):
        raise RunnerError("context_id values must be unique")
    environments = [attempt["environment"] for attempt in attempts]
    if any(environment != environments[0] for environment in environments[1:]):
        raise RunnerError("all attempts must use the same declared environment")

    bundles = args.output_root / "bundle"
    if bundles.exists():
        shutil.rmtree(bundles)
    bundles.mkdir(parents=True)

    before_zip = bundles / "screenshots-before.zip"
    after_zip = bundles / "screenshots-after.zip"
    network_zip = bundles / "network-archives.zip"
    before_states_path = bundles / "states-before.json"
    after_states_path = bundles / "states-after.json"
    trace_path = bundles / "transitions.ttrace.jsonl"

    before_members = []
    after_members = []
    network_members = []
    before_states = []
    after_states = []
    trace_lines = []
    for directory, attempt in zip(attempt_dirs, attempts):
        aid = attempt["attempt_id"]
        before = attempt["checkpoints"]["before"]
        before_members.append((safe_child(directory, before["screenshot_path"]), f"{aid}/before.png"))
        for checkpoint_name in ("after_currency", "after_history"):
            checkpoint_value = attempt["checkpoints"][checkpoint_name]
            after_members.append(
                (
                    safe_child(directory, checkpoint_value["screenshot_path"]),
                    f"{aid}/{checkpoint_name}.png",
                )
            )
        network = attempt["artifacts"]["network_archive"]
        network_members.append((safe_child(directory, network["path"]), f"{aid}/network.har"))
        before_states.append(
            {"attempt_id": aid, **attempt["checkpoints"]["before"]["state"]}
        )
        after_states.append(
            {"attempt_id": aid, **attempt["checkpoints"]["after_history"]["state"]}
        )
        trace_lines.extend(
            safe_child(directory, attempt["artifacts"]["transition_trace"]["path"])
            .read_text(encoding="utf-8")
            .splitlines()
        )

    zip_files(before_zip, before_members)
    zip_files(after_zip, after_members)
    zip_files(network_zip, network_members)
    write_json(before_states_path, before_states)
    write_json(after_states_path, after_states)
    trace_path.write_text("\n".join(trace_lines) + "\n", encoding="utf-8")

    artifacts = [
        final_artifact("screenshot_before", before_zip, args.output_root),
        final_artifact("screenshot_after", after_zip, args.output_root),
        final_artifact("network_archive", network_zip, args.output_root),
        final_artifact("state_before", before_states_path, args.output_root),
        final_artifact("state_after", after_states_path, args.output_root),
        final_artifact("transition_trace", trace_path, args.output_root),
    ]
    capture_attempts = []
    for attempt in attempts:
        capture_attempts.append(
            {
                "attempt_id": attempt["attempt_id"],
                "context_id": attempt["context_id"],
                "result": attempt["result"],
                "state_before": attempt["checkpoints"]["before"]["state"],
                "state_after": attempt["checkpoints"]["after_history"]["state"],
            }
        )

    capture = {
        **template,
        "status": "executed",
        "payment_submitted": False,
        "reservation_created": False,
        "secrets_redacted": True,
        "started_at": min(attempt["started_at"] for attempt in attempts),
        "completed_at": max(attempt["completed_at"] for attempt in attempts),
        "environment": environments[0],
        "attempts": capture_attempts,
        "artifacts": artifacts,
        "redaction_attestation": {
            "har_redacted_by_runner": True,
            "screenshots_reviewed_by_operator": True,
            "confirmed_at": utc_now(),
        },
        "note": (
            "Packaged by the operator-guided Playwright runner. "
            "Integrity and completeness do not confirm a defect."
        ),
    }
    capture_path = args.output_root / "capture.json"
    write_json(capture_path, capture)
    manifest = {
        "manifest_version": "proofpath-lqa-browser-evidence/0.1",
        "run_id": RUN_ID,
        "integrity_only": True,
        "truth_claim": False,
        "capture_path": capture_path.name,
        "capture_sha256": sha256_file(capture_path),
        "artifacts": artifacts,
    }
    write_json(args.output_root / "evidence-manifest.json", manifest)
    print(json.dumps({"capture": str(capture_path), "attempts": len(attempts)}, indent=2))
    return capture


def plan(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_json(args.profile)
    template = load_json(args.capture_template)
    validate_profile(profile)
    validate_template(template)
    value = {
        "mode": "plan",
        "browser_imported": False,
        "target_interaction": False,
        "run_id": RUN_ID,
        "profile_id": PROFILE_ID,
        "minimum_independent_attempts": profile["minimum_independent_attempts"],
        "operator_guided": True,
        "automated_clicks": False,
        "dangerous_requests_aborted": True,
        "highest_automatic_result": "READY_FOR_REVIEW / F3",
        "confirmed_defect": False,
    }
    print(json.dumps(value, indent=2, sort_keys=True))
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", type=Path, required=True)
    common.add_argument("--capture-template", type=Path, required=True)

    plan_parser = subparsers.add_parser("plan", parents=[common])
    plan_parser.set_defaults(func=plan)

    run_parser = subparsers.add_parser("run", parents=[common])
    run_parser.add_argument("--listing-url", required=True)
    run_parser.add_argument("--attempt-id", required=True)
    run_parser.add_argument("--output-root", type=Path, required=True)
    run_parser.add_argument("--locale", default="en-US")
    run_parser.add_argument("--timezone", default="Europe/Istanbul")
    run_parser.add_argument("--ip-country", default="TR")
    run_parser.add_argument("--authenticated", action="store_true")
    run_parser.add_argument("--acknowledge-safe-scope", action="store_true")
    run_parser.set_defaults(func=execute_attempt)

    finalize_parser = subparsers.add_parser("finalize", parents=[common])
    finalize_parser.add_argument("--output-root", type=Path, required=True)
    finalize_parser.add_argument("--confirm-screenshots-reviewed", action="store_true")
    finalize_parser.set_defaults(func=finalize)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, RunnerError) as exc:
        print(f"FAIL lotus Playwright capture runner: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
