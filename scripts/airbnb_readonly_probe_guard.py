#!/usr/bin/env python3
"""Run the read-only Airbnb probe and guard against recommendation-price false positives."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ORIGINAL = Path(__file__).with_name("airbnb_readonly_probe.py")
UNAVAILABLE_MARKERS = (
    "add dates for prices",
    "those dates are not available",
    "this listing is no longer available",
    "page not found",
)
PRICE_ANCHORS = ("show price breakdown", "reserve")
CURRENCY_PATTERNS = {
    "TRY": re.compile(r"(?:₺\s?[0-9]|\bTRY\b)", re.I),
    "EUR": re.compile(r"(?:€\s?[0-9]|\bEUR\b)", re.I),
    "USD": re.compile(r"(?:\$\s?[0-9]|\bUSD\b)", re.I),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_price_context(text: str, requested_currency: str) -> tuple[bool, str]:
    lowered = text.lower()
    if any(marker in lowered for marker in UNAVAILABLE_MARKERS):
        return False, "listing dates unavailable or listing page missing"

    lines = [" ".join(line.split()) for line in text.splitlines()]
    anchor_indexes = [
        index
        for index, line in enumerate(lines)
        if any(anchor in line.lower() for anchor in PRICE_ANCHORS)
    ]
    if not anchor_indexes:
        return False, "target reservation price block not found"

    anchor = anchor_indexes[0]
    start = max(0, anchor - 18)
    end = min(len(lines), anchor + 18)
    excerpt = " | ".join(line for line in lines[start:end] if line)
    pattern = CURRENCY_PATTERNS.get(requested_currency)
    if pattern is None or not pattern.search(excerpt):
        return False, "requested currency absent from target reservation price block"
    return True, excerpt[:1800]


def refresh_manifest(root: Path) -> None:
    manifest: list[dict[str, Any]] = []
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listing-url", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    subprocess.run(
        [
            sys.executable,
            str(ORIGINAL),
            "--listing-url",
            args.listing_url,
            "--output-root",
            str(args.output_root),
        ],
        check=True,
    )

    report_path = args.output_root / "probe-result.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    for attempt in report["attempts"]:
        contexts_ok = True
        reasons: list[str] = []
        for state in attempt["states"]:
            text_path = (
                args.output_root
                / "attempts"
                / attempt["attempt_id"]
                / f"{state['label']}.txt"
            )
            text = text_path.read_text(encoding="utf-8")
            detected, detail = target_price_context(text, state["requested_currency"])
            state["target_price_context_detected"] = detected
            if detected:
                state["target_price_excerpt"] = detail
            else:
                state["target_price_context_reason"] = detail
                contexts_ok = False
                reasons.append(f"{state['label']}: {detail}")

        if not contexts_ok:
            attempt["outcome"] = "inconclusive"
            attempt["reason"] = "; ".join(reasons)

    report["outcomes"] = [attempt["outcome"] for attempt in report["attempts"]]
    report["normalized_signatures"] = [
        [state["inferred_visible_currency"] for state in attempt["states"]]
        for attempt in report["attempts"]
    ]
    if (
        report["outcomes"] == ["inconsistent", "inconsistent"]
        and report["normalized_signatures"][0] == report["normalized_signatures"][1]
    ):
        report["evidence_grade"] = "F3"
    elif any(attempt["states"] for attempt in report["attempts"]):
        report["evidence_grade"] = "F2"
    else:
        report["evidence_grade"] = "F0"
    report["classifier_revision"] = "target-price-context-v2"
    report["confirmed_defect"] = False
    report["payment_submitted"] = False
    report["reservation_created"] = False

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    refresh_manifest(args.output_root)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
