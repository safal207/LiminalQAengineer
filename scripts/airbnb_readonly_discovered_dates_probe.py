#!/usr/bin/env python3
"""Discover a valid public Airbnb date range, then run guarded history and reload probes.

Safety boundary: public unauthenticated listing only. The script never logs in, clicks
Reserve, submits a form, contacts a host, enters payment data, or creates a reservation.
Date selection is represented only by public URL query parameters.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Browser, Page, sync_playwright

from airbnb_readonly_probe_guard import refresh_manifest, target_price_context

GUARD = Path(__file__).with_name("airbnb_readonly_probe_guard.py")
UNAVAILABLE_MARKERS = (
    "add dates for prices",
    "those dates are not available",
    "this listing is no longer available",
    "page not found",
)
DATE_LABEL_RE = re.compile(r"^(\d{1,2}), [A-Za-z]+, ([A-Za-z]+) (\d{4})\.")
MIN_NIGHTS_RE = re.compile(r"there is a (\d+) night minimum stay requirement", re.I)
EUR_AMOUNT_RE = re.compile(r"€\s?[0-9][0-9.,\s]*")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_listing_url(url: str, **updates: str | None) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in {"airbnb.com", "www.airbnb.com"}:
        raise ValueError("only public HTTPS airbnb.com listing URLs are allowed")
    if not re.fullmatch(r"/rooms/\d+", parts.path.rstrip("/")):
        raise ValueError("URL must point to one public Airbnb /rooms/<id> listing")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key in ("check_in", "check_out", "currency"):
        query.pop(key, None)
    query.setdefault("guests", "1")
    query.setdefault("adults", "1")
    for key, value in updates.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def parse_day(label: str) -> date | None:
    match = DATE_LABEL_RE.match(label)
    if not match:
        return None
    return datetime.strptime(
        f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y"
    ).date()


def save_page(page: Page, root: Path, name: str) -> str:
    root.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(7000)
    text = page.locator("body").inner_text(timeout=15000)
    (root / f"{name}.txt").write_text(text, encoding="utf-8")
    (root / f"{name}.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(root / f"{name}.png"), full_page=True, animations="disabled")
    return text


def calendar_days(page: Page) -> list[dict[str, Any]]:
    locator = page.locator(
        '[data-testid="inline-availability-calendar"] [role="button"][aria-label]'
    )
    values: list[dict[str, Any]] = []
    for index in range(locator.count()):
        node = locator.nth(index)
        label = node.get_attribute("aria-label") or ""
        parsed = parse_day(label)
        if parsed is None:
            continue
        values.append(
            {
                "date": parsed.isoformat(),
                "label": label,
                "aria_disabled": node.get_attribute("aria-disabled") == "true",
            }
        )
    return values


def candidate_pairs(days: list[dict[str, Any]]) -> list[tuple[date, date, str]]:
    parsed = [
        (date.fromisoformat(item["date"]), item["label"], item["aria_disabled"])
        for item in days
    ]
    checkins = [
        (day, label)
        for day, label, disabled in parsed
        if not disabled
        and "select as check-in date" in label.lower()
        and "no eligible checkout" not in label.lower()
    ]
    checkout_only = [
        day
        for day, label, disabled in parsed
        if not disabled and "only available for checkout" in label.lower()
    ]

    candidates: list[tuple[date, date, str]] = []
    for checkin, label in checkins:
        for checkout in checkout_only:
            if checkin < checkout <= checkin + timedelta(days=31):
                candidates.append((checkin, checkout, "calendar checkout-only boundary"))
                break
        minimum = MIN_NIGHTS_RE.search(label)
        if minimum:
            checkout = checkin + timedelta(days=int(minimum.group(1)))
            day_map = {day: (day_label, disabled) for day, day_label, disabled in parsed}
            target = day_map.get(checkout)
            if target and not target[1] and "unavailable" not in target[0].lower():
                candidates.append((checkin, checkout, "calendar minimum-night fallback"))

    unique: list[tuple[date, date, str]] = []
    seen: set[tuple[date, date]] = set()
    for item in sorted(candidates, key=lambda value: (value[0], value[1])):
        key = (item[0], item[1])
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique[:6]


def new_context(browser: Browser):
    return browser.new_context(
        locale="en-US",
        timezone_id="Europe/Istanbul",
        viewport={"width": 1440, "height": 1100},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )


def discover_dates(browser: Browser, listing_url: str, root: Path) -> dict[str, Any]:
    context = new_context(browser)
    page = context.new_page()
    base_url = public_listing_url(listing_url, currency="TRY")
    result: dict[str, Any] = {
        "started_at": utc_now(),
        "base_url": base_url,
        "candidates": [],
        "selected": None,
    }
    try:
        response = page.goto(base_url, wait_until="domcontentloaded", timeout=90000)
        text = save_page(page, root, "calendar-discovery")
        result["http_status"] = response.status if response else None
        result["challenge_or_missing"] = any(
            marker in text.lower() for marker in UNAVAILABLE_MARKERS[2:]
        )
        days = calendar_days(page)
        result["calendar_days"] = days
        pairs = candidate_pairs(days)
        for checkin, checkout, source in pairs:
            resolved = public_listing_url(
                listing_url,
                check_in=checkin.isoformat(),
                check_out=checkout.isoformat(),
                currency="TRY",
            )
            validation = {
                "check_in": checkin.isoformat(),
                "check_out": checkout.isoformat(),
                "source": source,
                "url": resolved,
            }
            try:
                response = page.goto(resolved, wait_until="domcontentloaded", timeout=90000)
                candidate_text = save_page(
                    page, root, f"candidate-{len(result['candidates']) + 1}"
                )
                detected, detail = target_price_context(candidate_text, "TRY")
                validation.update(
                    {
                        "http_status": response.status if response else None,
                        "target_price_context_detected": detected,
                        "detail": detail[:1800],
                    }
                )
            except Exception as exc:
                validation.update(
                    {
                        "target_price_context_detected": False,
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
            result["candidates"].append(validation)
            if validation["target_price_context_detected"]:
                result["selected"] = validation
                break
    finally:
        context.close()
    result["completed_at"] = utc_now()
    (root / "date-discovery.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def reload_probe(browser: Browser, resolved_url: str, root: Path) -> dict[str, Any]:
    context = new_context(browser)
    page = context.new_page()
    eur_url = public_listing_url(
        resolved_url,
        check_in=dict(parse_qsl(urlsplit(resolved_url).query))["check_in"],
        check_out=dict(parse_qsl(urlsplit(resolved_url).query))["check_out"],
        currency="EUR",
    )
    value: dict[str, Any] = {"started_at": utc_now(), "url": eur_url}
    try:
        before_response = page.goto(eur_url, wait_until="domcontentloaded", timeout=90000)
        before_text = save_page(page, root, "01-before-reload-eur")
        before_ok, before_detail = target_price_context(before_text, "EUR")
        reload_response = page.reload(wait_until="domcontentloaded", timeout=90000)
        after_text = save_page(page, root, "02-after-reload-eur")
        after_ok, after_detail = target_price_context(after_text, "EUR")
        before_amount = (EUR_AMOUNT_RE.search(before_detail) or [None])[0] if before_ok else None
        after_amount = (EUR_AMOUNT_RE.search(after_detail) or [None])[0] if after_ok else None
        value.update(
            {
                "before_http_status": before_response.status if before_response else None,
                "after_http_status": reload_response.status if reload_response else None,
                "before_target_price_context": before_ok,
                "after_target_price_context": after_ok,
                "before_amount": before_amount,
                "after_amount": after_amount,
                "outcome": "consistent"
                if before_ok and after_ok and before_amount == after_amount
                else "inconclusive",
                "confirmed_defect": False,
            }
        )
    except Exception as exc:
        value.update(
            {
                "outcome": "inconclusive",
                "runtime_error": f"{type(exc).__name__}: {exc}",
                "confirmed_defect": False,
            }
        )
    finally:
        context.close()
    value["completed_at"] = utc_now()
    (root / "reload-probe.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return value


def write_discovery_only_report(output_root: Path, listing_url: str, discovery: dict[str, Any]) -> None:
    report = {
        "run_id": "ABNB-DISCOVERED-DATES",
        "target": listing_url,
        "mode": "real_public_read_only_date_discovery",
        "attempts": [],
        "outcomes": ["inconclusive"],
        "normalized_signatures": [],
        "evidence_grade": "F0",
        "date_discovery": discovery,
        "confirmed_defect": False,
        "payment_submitted": False,
        "reservation_created": False,
    }
    (output_root / "probe-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    refresh_manifest(output_root)
    print(json.dumps(report, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listing-url", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {args.output_root}")

    with tempfile.TemporaryDirectory(prefix="airbnb-discovery-") as temp_name:
        discovery_root = Path(temp_name)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"]
            )
            discovery = discover_dates(browser, args.listing_url, discovery_root)
            selected = discovery.get("selected")
            browser.close()

        if not selected:
            args.output_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(discovery_root, args.output_root / "discovery")
            write_discovery_only_report(args.output_root, args.listing_url, discovery)
            return 0

        resolved_url = selected["url"]
        subprocess.run(
            [
                sys.executable,
                str(GUARD),
                "--listing-url",
                resolved_url,
                "--output-root",
                str(args.output_root),
            ],
            check=True,
        )
        shutil.copytree(discovery_root, args.output_root / "discovery")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"]
        )
        reload_result = reload_probe(browser, resolved_url, args.output_root / "reload")
        browser.close()

    report_path = args.output_root / "probe-result.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["date_discovery"] = discovery
    report["resolved_target"] = resolved_url
    report["reload_probe"] = reload_result
    report["classifier_revision"] = "target-price-context-v3-discovered-dates-reload"
    report["confirmed_defect"] = False
    report["payment_submitted"] = False
    report["reservation_created"] = False
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    refresh_manifest(args.output_root)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
