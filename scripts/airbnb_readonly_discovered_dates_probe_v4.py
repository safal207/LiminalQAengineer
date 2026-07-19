#!/usr/bin/env python3
"""Compatibility layer for Airbnb calendar labels used by discovered-date probe v3."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import airbnb_readonly_discovered_dates_probe as base

START_DATE_PHRASES = ("select as check-in date", "select as start date")


def candidate_pairs_v4(days: list[dict[str, Any]]) -> list[tuple[date, date, str]]:
    parsed = [
        (date.fromisoformat(item["date"]), item["label"], item["aria_disabled"])
        for item in days
    ]
    checkins = [
        (day, label)
        for day, label, disabled in parsed
        if not disabled
        and any(phrase in label.lower() for phrase in START_DATE_PHRASES)
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
                candidates.append((checkin, checkout, "calendar checkout-only boundary v4"))
                break

        minimum = base.MIN_NIGHTS_RE.search(label)
        if minimum:
            checkout = checkin + timedelta(days=int(minimum.group(1)))
            day_map = {day: (day_label, disabled) for day, day_label, disabled in parsed}
            target = day_map.get(checkout)
            if target and not target[1] and "unavailable" not in target[0].lower():
                candidates.append((checkin, checkout, "calendar minimum-night fallback v4"))

    unique: list[tuple[date, date, str]] = []
    seen: set[tuple[date, date]] = set()
    for item in sorted(candidates, key=lambda value: (value[0], value[1])):
        key = (item[0], item[1])
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique[:6]


def output_root_from_argv() -> Path | None:
    try:
        index = sys.argv.index("--output-root")
        return Path(sys.argv[index + 1])
    except (ValueError, IndexError):
        return None


def main() -> int:
    base.candidate_pairs = candidate_pairs_v4
    code = base.main()
    root = output_root_from_argv()
    if code == 0 and root is not None:
        report_path = root / "probe-result.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["classifier_revision"] = "target-price-context-v4-calendar-labels"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            base.refresh_manifest(root)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
