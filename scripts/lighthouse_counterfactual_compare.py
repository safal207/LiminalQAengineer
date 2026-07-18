#!/usr/bin/env python3
"""Compare two bounded Lighthouse variants and emit a LiminalQA counterfactual packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRICS = {
    "first_contentful_paint_ms": "first-contentful-paint",
    "largest_contentful_paint_ms": "largest-contentful-paint",
    "speed_index_ms": "speed-index",
    "total_blocking_time_ms": "total-blocking-time",
    "cumulative_layout_shift": "cumulative-layout-shift",
}
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def find_reports(folder: Path) -> list[Path]:
    reports: list[Path] = []
    for path in sorted(folder.rglob("*.json")):
        try:
            data = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(data.get("audits"), dict) and isinstance(data.get("categories"), dict):
            reports.append(path)
    if not reports:
        raise FileNotFoundError(f"No Lighthouse reports found below {folder}")
    return reports


def numeric_audit(report: dict[str, Any], audit_id: str) -> float | None:
    audit = report.get("audits", {}).get(audit_id, {})
    value = audit.get("numericValue") if isinstance(audit, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def redirect_duration(report: dict[str, Any]) -> float | None:
    audit = report.get("audits", {}).get("document-latency-insight", {})
    details = audit.get("details", {}) if isinstance(audit, dict) else {}
    debug = details.get("debugData", {}) if isinstance(details, dict) else {}
    value = debug.get("redirectDuration") if isinstance(debug, dict) else None
    if isinstance(value, (int, float)):
        return float(value)
    return numeric_audit(report, "redirects")


def score(report: dict[str, Any], category: str) -> float | None:
    raw = report.get("categories", {}).get(category, {})
    value = raw.get("score") if isinstance(raw, dict) else None
    return round(float(value) * 100.0, 2) if isinstance(value, (int, float)) else None


def median(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if isinstance(value, (int, float))]
    return round(float(statistics.median(cleaned)), 3) if cleaned else None


def summarize_variant(folder: Path, variant_id: str) -> dict[str, Any]:
    report_paths = find_reports(folder)
    rows = []
    for path in report_paths:
        report = load_json(path)
        row: dict[str, Any] = {
            "file": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "requested_url": report.get("requestedUrl"),
            "final_url": report.get("finalUrl"),
            "fetch_time": report.get("fetchTime"),
            "lighthouse_version": report.get("lighthouseVersion"),
            "redirect_duration_ms": redirect_duration(report),
        }
        row.update({name: numeric_audit(report, audit_id) for name, audit_id in METRICS.items()})
        row["categories"] = {category: score(report, category) for category in CATEGORIES}
        rows.append(row)

    medians = {
        name: median([row.get(name) for row in rows])
        for name in (*METRICS.keys(), "redirect_duration_ms")
    }
    medians["categories"] = {
        category: median([row["categories"].get(category) for row in rows])
        for category in CATEGORIES
    }
    return {
        "variant_id": variant_id,
        "run_count": len(rows),
        "medians": medians,
        "runs": rows,
    }


def delta(redirect: float | None, direct: float | None) -> dict[str, float | None]:
    if redirect is None or direct is None:
        return {"direct_minus_redirect": None, "improvement_percent": None}
    difference = direct - redirect
    improvement = ((redirect - direct) / redirect * 100.0) if redirect else None
    return {
        "direct_minus_redirect": round(difference, 3),
        "improvement_percent": round(improvement, 2) if improvement is not None else None,
    }


def build_packet(experiment: dict[str, Any], redirect: dict[str, Any], direct: dict[str, Any]) -> dict[str, Any]:
    metric_effects = {
        metric: delta(redirect["medians"].get(metric), direct["medians"].get(metric))
        for metric in (*METRICS.keys(), "redirect_duration_ms")
    }
    category_effects = {
        category: delta(
            redirect["medians"]["categories"].get(category),
            direct["medians"]["categories"].get(category),
        )
        for category in CATEGORIES
    }

    time_metrics = (
        "first_contentful_paint_ms",
        "largest_contentful_paint_ms",
        "speed_index_ms",
        "total_blocking_time_ms",
    )
    better_count = sum(
        1
        for metric in time_metrics
        if isinstance(metric_effects[metric]["direct_minus_redirect"], (int, float))
        and metric_effects[metric]["direct_minus_redirect"] < 0
    )
    lcp_delta = metric_effects["largest_contentful_paint_ms"]["direct_minus_redirect"]
    redirect_removed = (
        (redirect["medians"].get("redirect_duration_ms") or 0) > 0
        and (direct["medians"].get("redirect_duration_ms") or 0) == 0
    )

    if redirect_removed and isinstance(lcp_delta, (int, float)) and lcp_delta <= -300 and better_count >= 3:
        verdict = "SUPPORTED"
    elif redirect_removed and better_count >= 2:
        verdict = "MIXED_SUPPORT"
    else:
        verdict = "NOT_SUPPORTED"

    return {
        "schema_version": "liminalqa-counterfactual-result-v1",
        "experiment": experiment,
        "verdict": verdict,
        "confidence": "MEDIUM" if redirect["run_count"] >= 3 and direct["run_count"] >= 3 else "LOW",
        "variants": {
            "redirect_root": redirect,
            "direct_ru": direct,
        },
        "effects": {
            "metrics": metric_effects,
            "categories": category_effects,
            "time_metrics_improved": better_count,
            "redirect_removed": redirect_removed,
        },
        "interpretation": (
            "The direct URL removes the observed redirect. Loading metrics determine whether that removal "
            "materially improves the page on this runner; remaining delay is attributed to other causes."
        ),
        "boundaries": {
            "passive_public_navigation": True,
            "authenticated_testing": False,
            "active_security_testing": False,
            "financial_operations": False,
            "field_performance_claim": False,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def fmt(value: Any, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def render(packet: dict[str, Any]) -> str:
    redirect = packet["variants"]["redirect_root"]["medians"]
    direct = packet["variants"]["direct_ru"]["medians"]
    effects = packet["effects"]["metrics"]
    lines = [
        "# LiminalQA · Tradernet redirect counterfactual",
        "",
        f"**Verdict:** {packet['verdict']}  ",
        f"**Confidence:** {packet['confidence']}  ",
        f"**Runs:** {packet['variants']['redirect_root']['run_count']} + {packet['variants']['direct_ru']['run_count']}",
        "",
        "## Median mobile metrics",
        "",
        "| Metric | Root with redirect | Direct Russian URL | Direct − root | Improvement |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "redirect_duration_ms": "Redirect duration (ms)",
        "first_contentful_paint_ms": "FCP (ms)",
        "largest_contentful_paint_ms": "LCP (ms)",
        "speed_index_ms": "Speed Index (ms)",
        "total_blocking_time_ms": "TBT (ms)",
        "cumulative_layout_shift": "CLS",
    }
    for key in labels:
        effect = effects[key]
        lines.append(
            f"| {labels[key]} | {fmt(redirect.get(key))} | {fmt(direct.get(key))} | "
            f"{fmt(effect.get('direct_minus_redirect'))} | {fmt(effect.get('improvement_percent'), '%')} |"
        )
    lines.extend(
        [
            "",
            "## Causal reading",
            "",
            f"- Redirect removed: **{str(packet['effects']['redirect_removed']).lower()}**.",
            f"- Faster time metrics: **{packet['effects']['time_metrics_improved']}/4**.",
            "- A supported result means the redirect contributes measurable delay; it does not explain the remaining shared-runtime and late-LCP costs.",
            "",
            "## Evidence boundary",
            "",
            "> Six passive public navigations on one GitHub-hosted runner. No authentication, API calls, trading operations, fuzzing or load testing.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--redirect-dir", required=True)
    parser.add_argument("--direct-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    experiment = load_json(Path(args.experiment))
    redirect = summarize_variant(Path(args.redirect_dir), "redirect_root")
    direct = summarize_variant(Path(args.direct_dir), "direct_ru")
    packet = build_packet(experiment, redirect, direct)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "counterfactual-result.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "counterfactual-summary.md").write_text(render(packet), encoding="utf-8")
    print(json.dumps({"verdict": packet["verdict"], "effects": packet["effects"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
