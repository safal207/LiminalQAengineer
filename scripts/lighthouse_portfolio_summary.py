#!/usr/bin/env python3
"""Aggregate bounded LiminalQA Lighthouse packets across a public domain portfolio."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def find_packets(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    packets: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.rglob("decision-packet.json")):
        try:
            packet = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if packet.get("schema_version") == "liminalqa-lighthouse-decision-v1":
            packets.append((path, packet))
    if not packets:
        raise FileNotFoundError(f"No LiminalQA Lighthouse decision packets found in {root}")
    return packets


def numeric_metric(packet: dict[str, Any], key: str) -> float | None:
    metrics = packet.get("core_web_metrics", {})
    if not isinstance(metrics, dict):
        return None
    item = metrics.get(key, {})
    if not isinstance(item, dict):
        return None
    value = item.get("numeric_value")
    return float(value) if isinstance(value, (int, float)) else None


def category_score(packet: dict[str, Any], key: str) -> int | None:
    categories = packet.get("categories", {})
    if not isinstance(categories, dict):
        return None
    item = categories.get(key, {})
    if not isinstance(item, dict):
        return None
    value = item.get("score")
    return int(value) if isinstance(value, (int, float)) else None


def build_portfolio(packets: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    recurring = Counter()

    for path, packet in packets:
        findings = packet.get("top_findings", [])
        if isinstance(findings, list):
            recurring.update(
                finding.get("audit_id")
                for finding in findings
                if isinstance(finding, dict) and isinstance(finding.get("audit_id"), str)
            )

        target = packet.get("target", {})
        evidence = packet.get("evidence", {})
        targets.append(
            {
                "artifact_path": str(path),
                "requested_url": target.get("requested_url") if isinstance(target, dict) else None,
                "final_url": target.get("final_url") if isinstance(target, dict) else None,
                "verdict": packet.get("verdict"),
                "severity": packet.get("severity"),
                "scores": {
                    "performance": category_score(packet, "performance"),
                    "accessibility": category_score(packet, "accessibility"),
                    "best_practices": category_score(packet, "best-practices"),
                    "seo": category_score(packet, "seo"),
                },
                "metrics_ms": {
                    "fcp": numeric_metric(packet, "first_contentful_paint"),
                    "lcp": numeric_metric(packet, "largest_contentful_paint"),
                    "tbt": numeric_metric(packet, "total_blocking_time"),
                },
                "cls": numeric_metric(packet, "cumulative_layout_shift"),
                "evidence_sha256": evidence.get("sha256") if isinstance(evidence, dict) else None,
                "fetch_time": evidence.get("fetch_time") if isinstance(evidence, dict) else None,
            }
        )

    targets.sort(key=lambda item: (item.get("final_url") or item.get("requested_url") or ""))
    warning_count = sum(1 for item in targets if item.get("verdict") != "PASS")

    performance_values = [
        item["scores"]["performance"]
        for item in targets
        if isinstance(item.get("scores", {}).get("performance"), int)
    ]
    lcp_values = [
        item["metrics_ms"]["lcp"]
        for item in targets
        if isinstance(item.get("metrics_ms", {}).get("lcp"), (int, float))
    ]

    return {
        "schema_version": "liminalqa-lighthouse-portfolio-v1",
        "run_kind": "passive_public_domain_quality_portfolio",
        "verdict": "PASS" if warning_count == 0 else "WARN",
        "target_count": len(targets),
        "warning_count": warning_count,
        "targets": targets,
        "portfolio_metrics": {
            "average_performance_score": round(sum(performance_values) / len(performance_values), 1)
            if performance_values
            else None,
            "slowest_lcp_ms": max(lcp_values) if lcp_values else None,
            "fastest_lcp_ms": min(lcp_values) if lcp_values else None,
        },
        "recurring_findings": [
            {"audit_id": audit_id, "target_count": count}
            for audit_id, count in recurring.most_common(12)
            if count > 1
        ],
        "boundaries": {
            "active_security_testing": False,
            "authenticated_testing": False,
            "api_testing": False,
            "financial_operations": False,
            "fuzzing": False,
            "load_testing": False,
            "vulnerability_claim": False,
            "statement": (
                "This portfolio compares one passive Lighthouse navigation per allowlisted public "
                "target. Inventory membership is not proof of common ownership or authorization."
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def fmt_seconds(value: Any) -> str:
    return f"{float(value) / 1000.0:.2f} s" if isinstance(value, (int, float)) else "n/a"


def render_markdown(portfolio: dict[str, Any]) -> str:
    lines = [
        "# LiminalQA · Tradernet public domain portfolio",
        "",
        f"**Verdict:** {portfolio['verdict']}  ",
        f"**Targets:** {portfolio['target_count']}  ",
        f"**Targets with warnings:** {portfolio['warning_count']}",
        "",
        "## Cross-domain scorecard",
        "",
        "| Final URL | Perf | A11y | Best practices | SEO | LCP | TBT | CLS | Verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for target in portfolio["targets"]:
        scores = target["scores"]
        metrics = target["metrics_ms"]
        cls = target.get("cls")
        cls_display = f"{cls:.3f}" if isinstance(cls, (int, float)) else "n/a"
        lines.append(
            "| {url} | {perf} | {a11y} | {bp} | {seo} | {lcp} | {tbt} | {cls} | {verdict} |".format(
                url=target.get("final_url") or target.get("requested_url") or "unknown",
                perf=scores.get("performance", "n/a"),
                a11y=scores.get("accessibility", "n/a"),
                bp=scores.get("best_practices", "n/a"),
                seo=scores.get("seo", "n/a"),
                lcp=fmt_seconds(metrics.get("lcp")),
                tbt=fmt_seconds(metrics.get("tbt")),
                cls=cls_display,
                verdict=target.get("verdict", "UNKNOWN"),
            )
        )

    lines.extend(["", "## Repeated signals", ""])
    recurring = portfolio.get("recurring_findings", [])
    if recurring:
        for item in recurring:
            lines.append(f"- `{item['audit_id']}` appears in {item['target_count']} target packets.")
    else:
        lines.append("No finding appeared in more than one target packet.")

    metrics = portfolio.get("portfolio_metrics", {})
    lines.extend(
        [
            "",
            "## Portfolio reflection",
            "",
            f"- Average Performance score: **{metrics.get('average_performance_score') or 'n/a'}**",
            f"- Fastest LCP: **{fmt_seconds(metrics.get('fastest_lcp_ms'))}**",
            f"- Slowest LCP: **{fmt_seconds(metrics.get('slowest_lcp_ms'))}**",
            "",
            "> Passive public quality evidence only. No authentication, API calls, trading, fuzzing,",
            "> load testing, private data, or vulnerability claim.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    portfolio = build_portfolio(find_packets(Path(args.input_dir)))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "portfolio-summary.json").write_text(
        json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "portfolio-summary.md").write_text(
        render_markdown(portfolio),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
