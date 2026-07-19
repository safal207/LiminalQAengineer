#!/usr/bin/env python3
"""Read-only Airbnb currency/history probe.

This script visits one public listing in two fresh browser contexts. It never logs in,
submits a form, contacts a host, enters payment data, or creates a reservation. Currency
changes are performed only by navigating to public URLs with a currency query parameter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Browser, Page, sync_playwright

CURRENCIES = ("TRY", "EUR")
PRICE_PATTERNS = {
    "TRY": re.compile(r"(?:₺\s?[0-9][0-9.,\s]*|[0-9][0-9.,\s]*\s?(?:TRY|₺))", re.I),
    "EUR": re.compile(r"(?:€\s?[0-9][0-9.,\s]*|[0-9][0-9.,\s]*\s?(?:EUR|€))", re.I),
    "USD": re.compile(r"(?:\$\s?[0-9][0-9.,\s]*|[0-9][0-9.,\s]*\s?USD)", re.I),
}
CHALLENGE_MARKERS = (
    "verify you are human",
    "captcha",
    "access denied",
    "unusual traffic",
    "temporarily blocked",
    "robot",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def with_currency(url: str, currency: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in {"airbnb.com", "www.airbnb.com"}:
        raise ValueError("only public HTTPS airbnb.com URLs are allowed")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["currency"] = currency
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_currency(counts: dict[str, int]) -> str:
    nonzero = {key: value for key, value in counts.items() if value > 0}
    if not nonzero:
        return "unknown"
    best = max(nonzero.values())
    winners = sorted(key for key, value in nonzero.items() if value == best)
    return winners[0] if len(winners) == 1 else "mixed"


def snapshot(page: Page, label: str, requested_currency: str, outdir: Path) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(7000)
    title = page.title()
    text = page.locator("body").inner_text(timeout=15000)
    lowered = text.lower()
    counts = {currency: len(pattern.findall(text)) for currency, pattern in PRICE_PATTERNS.items()}
    screenshot = outdir / f"{label}.png"
    html_path = outdir / f"{label}.html"
    text_path = outdir / f"{label}.txt"
    page.screenshot(path=str(screenshot), full_page=True, animations="disabled")
    html_path.write_text(page.content(), encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    return {
        "label": label,
        "captured_at": utc_now(),
        "requested_currency": requested_currency,
        "inferred_visible_currency": infer_currency(counts),
        "visible_price_pattern_counts": counts,
        "title": title,
        "final_url": page.url,
        "challenge_detected": any(marker in lowered for marker in CHALLENGE_MARKERS),
        "body_text_length": len(text),
        "artifacts": {
            "screenshot": str(screenshot),
            "html": str(html_path),
            "text": str(text_path),
        },
    }


def navigate(page: Page, url: str) -> dict[str, Any]:
    response = page.goto(url, wait_until="domcontentloaded", timeout=90000)
    return {
        "requested_url": url,
        "http_status": response.status if response else None,
        "response_url": response.url if response else None,
    }


def classify(states: list[dict[str, Any]], runtime_errors: list[str]) -> tuple[str, str]:
    if runtime_errors or any(state["challenge_detected"] for state in states):
        return "inconclusive", "runtime error or anti-bot/interstitial detected"
    expected = ["TRY", "EUR", "TRY", "EUR"]
    observed = [state["inferred_visible_currency"] for state in states]
    if any(value in {"unknown", "mixed"} for value in observed):
        return "inconclusive", f"currency could not be inferred at every checkpoint: {observed}"
    if observed == expected:
        return "consistent", "visible currency followed URL currency across navigation and history"
    return "inconsistent", f"expected {expected}, observed {observed}"


def run_attempt(browser: Browser, listing_url: str, attempt_id: str, root: Path) -> dict[str, Any]:
    attempt_dir = root / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    request_failures: list[dict[str, str | None]] = []
    bad_responses: list[dict[str, Any]] = []

    context = browser.new_context(
        locale="en-US",
        timezone_id="Europe/Istanbul",
        viewport={"width": 1440, "height": 1100},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "requestfailed",
        lambda request: request_failures.append(
            {"url": request.url.split("?", 1)[0], "error": request.failure}
        ),
    )
    page.on(
        "response",
        lambda response: bad_responses.append(
            {"url": response.url.split("?", 1)[0], "status": response.status}
        )
        if response.status >= 400
        else None,
    )

    states: list[dict[str, Any]] = []
    navigation: list[dict[str, Any]] = []
    runtime_errors: list[str] = []
    try:
        try_url = with_currency(listing_url, "TRY")
        eur_url = with_currency(listing_url, "EUR")

        navigation.append(navigate(page, try_url))
        states.append(snapshot(page, "01-before-try", "TRY", attempt_dir))

        navigation.append(navigate(page, eur_url))
        states.append(snapshot(page, "02-after-eur", "EUR", attempt_dir))

        back_response = page.go_back(wait_until="domcontentloaded", timeout=90000)
        navigation.append(
            {
                "action": "go_back",
                "http_status": back_response.status if back_response else None,
                "response_url": back_response.url if back_response else page.url,
            }
        )
        states.append(snapshot(page, "03-history-back", "TRY", attempt_dir))

        forward_response = page.go_forward(wait_until="domcontentloaded", timeout=90000)
        navigation.append(
            {
                "action": "go_forward",
                "http_status": forward_response.status if forward_response else None,
                "response_url": forward_response.url if forward_response else page.url,
            }
        )
        states.append(snapshot(page, "04-history-forward", "EUR", attempt_dir))
    except Exception as exc:  # evidence must survive partial runs
        runtime_errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        context.close()

    outcome, reason = classify(states, runtime_errors) if len(states) == 4 else (
        "inconclusive",
        f"only {len(states)} of 4 checkpoints completed",
    )
    result = {
        "attempt_id": attempt_id,
        "started_and_completed_in_fresh_context": True,
        "states": states,
        "navigation": navigation,
        "outcome": outcome,
        "reason": reason,
        "runtime_errors": runtime_errors,
        "console_error_count": len(console_errors),
        "page_errors": page_errors[:50],
        "request_failures": request_failures[:100],
        "http_4xx_5xx": bad_responses[:100],
        "payment_submitted": False,
        "reservation_created": False,
    }
    (attempt_dir / "attempt.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listing-url", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.output_root
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        attempts = [
            run_attempt(browser, args.listing_url, "attempt-01", root),
            run_attempt(browser, args.listing_url, "attempt-02", root),
        ]
        browser.close()

    outcomes = [attempt["outcome"] for attempt in attempts]
    signatures = [
        [state["inferred_visible_currency"] for state in attempt["states"]]
        for attempt in attempts
    ]
    if outcomes == ["inconsistent", "inconsistent"] and signatures[0] == signatures[1]:
        evidence_grade = "F3"
    elif any(attempt["states"] for attempt in attempts):
        evidence_grade = "F2"
    else:
        evidence_grade = "F0"

    report = {
        "run_id": "ABNB-RUN-002-DOCKER",
        "started_at": started_at,
        "completed_at": utc_now(),
        "target": args.listing_url,
        "mode": "real_public_read_only_headless_browser",
        "attempts": attempts,
        "outcomes": outcomes,
        "normalized_signatures": signatures,
        "evidence_grade": evidence_grade,
        "confirmed_defect": False,
        "payment_submitted": False,
        "reservation_created": False,
        "truth_boundary": (
            "F2/F3 records reproducible browser evidence only. It does not establish expected "
            "Airbnb behavior, root cause, security impact, or a confirmed defect."
        ),
    }
    report_path = root / "probe-result.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    manifest = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            manifest.append(
                {
                    "path": str(path.relative_to(root)),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
