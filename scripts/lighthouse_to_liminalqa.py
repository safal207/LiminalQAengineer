#!/usr/bin/env python3
"""Convert a Lighthouse result into a bounded LiminalQA decision packet.

This adapter intentionally treats Lighthouse as a public web-quality signal.
It does not claim vulnerability discovery, penetration testing, or compliance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "liminalqa-lighthouse-decision-v1"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def normalize_and_validate_url(policy: dict[str, Any], raw_url: str) -> str:
    parsed = urlsplit(raw_url.strip())
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS targets are allowed")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Credentials and custom ports are not allowed")
    if parsed.query or parsed.fragment:
        raise ValueError("Query strings and fragments are not allowed")

    origin = f"{parsed.scheme}://{parsed.hostname or ''}"
    allowed_origins = set(policy.get("allowed_origins", []))
    if origin not in allowed_origins:
        raise ValueError(f"Origin is outside the audit allowlist: {origin}")

    path = parsed.path or "/"
    allowed_paths = set(policy.get("allowed_paths", []))
    if path not in allowed_paths:
        raise ValueError(f"Path is outside the audit allowlist: {path}")

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def find_lighthouse_report(input_dir: Path) -> Path:
    preferred = sorted(input_dir.glob("lhr-*.json"))
    candidates = preferred or sorted(input_dir.glob("*.json"))
    for candidate in candidates:
        try:
            data = load_json(candidate)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(data.get("categories"), dict) and isinstance(data.get("audits"), dict):
            return candidate
    raise FileNotFoundError(f"No Lighthouse result JSON found in {input_dir}")


def score_percent(category: dict[str, Any]) -> int:
    score = category.get("score")
    if not isinstance(score, (int, float)):
        return 0
    return round(max(0.0, min(1.0, float(score))) * 100)


def metric_value(audits: dict[str, Any], audit_id: str) -> dict[str, Any]:
    audit = audits.get(audit_id, {})
    if not isinstance(audit, dict):
        return {"id": audit_id, "display": None, "numeric_value": None}
    numeric = audit.get("numericValue")
    return {
        "id": audit_id,
        "title": audit.get("title"),
        "display": audit.get("displayValue"),
        "numeric_value": numeric if isinstance(numeric, (int, float)) else None,
    }


def top_findings(audits: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    ignored_modes = {"notApplicable", "manual", "informative"}
    for audit_id, raw in audits.items():
        if not isinstance(raw, dict):
            continue
        if raw.get("scoreDisplayMode") in ignored_modes:
            continue
        score = raw.get("score")
        if not isinstance(score, (int, float)) or score >= 1:
            continue
        details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
        savings_ms = details.get("overallSavingsMs")
        finding = {
            "audit_id": audit_id,
            "title": raw.get("title"),
            "description": raw.get("description"),
            "score": round(float(score), 3),
            "display_value": raw.get("displayValue"),
            "savings_ms": round(float(savings_ms), 1)
            if isinstance(savings_ms, (int, float))
            else None,
        }
        findings.append(finding)

    findings.sort(
        key=lambda item: (
            item["score"],
            -(item["savings_ms"] or 0),
            item["audit_id"],
        )
    )
    return findings[:limit]


def build_packet(policy: dict[str, Any], report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    categories = report.get("categories", {})
    audits = report.get("audits", {})
    if not isinstance(categories, dict) or not isinstance(audits, dict):
        raise ValueError("Invalid Lighthouse result: missing categories or audits")

    thresholds = policy.get("category_thresholds", {})
    category_results: dict[str, Any] = {}
    failed_categories: list[str] = []

    for category_id in ("performance", "accessibility", "best-practices", "seo"):
        raw_category = categories.get(category_id, {})
        if not isinstance(raw_category, dict):
            raw_category = {}
        score = score_percent(raw_category)
        threshold_fraction = thresholds.get(category_id, 0.0)
        threshold = round(float(threshold_fraction) * 100)
        status = "PASS" if score >= threshold else "WARN"
        if status != "PASS":
            failed_categories.append(category_id)
        category_results[category_id] = {
            "score": score,
            "threshold": threshold,
            "status": status,
        }

    verdict = "PASS" if not failed_categories else "WARN"
    largest_gap = max(
        (result["threshold"] - result["score"] for result in category_results.values()),
        default=0,
    )
    severity = "HIGH" if largest_gap >= 30 else "MEDIUM" if largest_gap >= 15 else "LOW"

    raw_bytes = report_path.read_bytes()
    requested_url = report.get("requestedUrl") or report.get("finalUrl") or ""
    final_url = report.get("finalUrl") or requested_url

    packet = {
        "schema_version": SCHEMA_VERSION,
        "run_kind": "public_web_quality_audit",
        "target": {
            "requested_url": requested_url,
            "final_url": final_url,
        },
        "verdict": verdict,
        "severity": severity,
        "merge_policy": "WARN" if verdict == "WARN" else "PASS",
        "confidence": "HIGH",
        "categories": category_results,
        "core_web_metrics": {
            "first_contentful_paint": metric_value(audits, "first-contentful-paint"),
            "largest_contentful_paint": metric_value(audits, "largest-contentful-paint"),
            "total_blocking_time": metric_value(audits, "total-blocking-time"),
            "cumulative_layout_shift": metric_value(audits, "cumulative-layout-shift"),
            "speed_index": metric_value(audits, "speed-index"),
        },
        "top_findings": top_findings(audits),
        "evidence": {
            "raw_report": report_path.name,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "lighthouse_version": report.get("lighthouseVersion"),
            "fetch_time": report.get("fetchTime"),
        },
        "boundaries": {
            "active_security_testing": False,
            "authenticated_testing": False,
            "financial_operations": False,
            "vulnerability_claim": False,
            "statement": (
                "This packet summarizes passive Lighthouse quality signals for an allowlisted "
                "public page. It is not a penetration test or a security vulnerability report."
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return packet


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# LiminalQA · Tradernet public Lighthouse audit",
        "",
        f"**Verdict:** {packet['verdict']}  ",
        f"**Quality severity:** {packet['severity']}  ",
        f"**Target:** `{packet['target']['final_url']}`",
        "",
        "## Category scores",
        "",
        "| Category | Score | Threshold | Status |",
        "|---|---:|---:|---|",
    ]
    for category, result in packet["categories"].items():
        lines.append(
            f"| {category} | {result['score']} | {result['threshold']} | {result['status']} |"
        )

    lines.extend(["", "## Core metrics", ""])
    for name, metric in packet["core_web_metrics"].items():
        display = metric.get("display") or "n/a"
        lines.append(f"- **{name}:** {display}")

    lines.extend(["", "## Highest-priority findings", ""])
    findings = packet.get("top_findings", [])
    if not findings:
        lines.append("No scored Lighthouse findings were returned.")
    else:
        for finding in findings[:5]:
            display = f" — {finding['display_value']}" if finding.get("display_value") else ""
            lines.append(
                f"- **{finding.get('title') or finding['audit_id']}** "
                f"(score {finding['score']}){display}"
            )

    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            f"Raw report SHA-256: `{packet['evidence']['sha256']}`",
            "",
            "> This is a public web-quality audit. It does not claim a security vulnerability,",
            "> access private data, authenticate, place trades, or perform active exploitation.",
            "",
        ]
    )
    return "\n".join(lines)


def command_validate(args: argparse.Namespace) -> int:
    policy = load_json(Path(args.policy))
    print(normalize_and_validate_url(policy, args.url))
    return 0


def command_report(args: argparse.Namespace) -> int:
    policy = load_json(Path(args.policy))
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = find_lighthouse_report(input_dir)
    packet = build_packet(policy, load_json(report_path), report_path)

    packet_path = output_dir / "decision-packet.json"
    summary_path = output_dir / "summary.md"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(render_markdown(packet), encoding="utf-8")

    print(f"Wrote {packet_path}")
    print(f"Wrote {summary_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-url")
    validate.add_argument("--policy", required=True)
    validate.add_argument("--url", required=True)
    validate.set_defaults(func=command_validate)

    report = subparsers.add_parser("report")
    report.add_argument("--policy", required=True)
    report.add_argument("--input-dir", required=True)
    report.add_argument("--output-dir", required=True)
    report.set_defaults(func=command_report)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
