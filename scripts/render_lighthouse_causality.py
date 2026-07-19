#!/usr/bin/env python3
"""Render an evidence-derived Lighthouse causality packet as Markdown."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def safe_text(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.1f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("\n", " ")


def time_text(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,.1f} ms"
    if isinstance(value, dict):
        parts = [
            f"{key}={safe_text(item)}" for key, item in value.items() if item is not None
        ]
        return ", ".join(parts) if parts else "n/a"
    return "n/a"


def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in graph.get("nodes", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def mermaid_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or node.get("id") or "node")
    time_value = time_text(node.get("time_ms"))
    return label if time_value == "n/a" else f"{label}\\n{time_value}"


def render(graph: dict[str, Any]) -> str:
    nodes = node_map(graph)
    evidence = graph.get("evidence", {})
    decision = nodes.get("decision", {}).get("metrics", {})
    verdict = decision.get("verdict", "UNCLASSIFIED")
    scores = decision.get("scores", {})

    lines = [
        "# LiminalQA · Lighthouse space-time causality graph",
        "",
        f"**Target:** `{graph.get('target', 'n/a')}`  ",
        f"**Evidence SHA-256:** `{evidence.get('sha256', 'n/a')}`  ",
        f"**Runs in packet:** {graph.get('run_count', 'n/a')}  ",
        f"**Verdict:** `{verdict}`",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    for node_id, item in nodes.items():
        label = mermaid_label(item).replace('"', "'")
        lines.append(f'  {node_id}["{label}"]')

    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        left = edge.get("from")
        right = edge.get("to")
        relation = str(edge.get("relation") or "relates_to").replace('"', "'")
        if left in nodes and right in nodes:
            lines.append(f"  {left} -->|{relation}| {right}")

    lines.extend(["```", "", "## Dominant path", ""])
    dominant = [item for item in graph.get("dominant_path", []) if item in nodes]
    lines.append(
        "`" + " → ".join(nodes[item].get("label", item) for item in dominant) + "`"
        if dominant
        else "No dominant path was derived from this report."
    )

    lines.extend(
        [
            "",
            "## Category scores",
            "",
            "| Category | Score | Threshold | Status |",
            "|---|---:|---:|---|",
        ]
    )
    thresholds = decision.get("thresholds", {})
    for category in ("performance", "accessibility", "best-practices", "seo"):
        score = scores.get(category)
        threshold = thresholds.get(category)
        status = (
            "UNKNOWN"
            if score is None or threshold is None
            else "PASS"
            if score >= threshold
            else "WARN"
        )
        lines.append(
            f"| {category} | {safe_text(score)} | {safe_text(threshold)} | {status} |"
        )

    lines.extend(
        [
            "",
            "## Ranked causes",
            "",
            "| Rank | Cause | Status | Evidence-derived reason | Next test |",
            "|---:|---|---|---|---|",
        ]
    )
    ranked = graph.get("ranked_causes", [])
    if ranked:
        for item in ranked:
            lines.append(
                f"| {item.get('rank')} | {safe_text(item.get('cause'))} | "
                f"{safe_text(item.get('status'))} | {safe_text(item.get('why'))} | "
                f"{safe_text(item.get('next_test'))} |"
            )
    else:
        lines.append(
            "| — | No supported cause | — | Current report lacks sufficient data | Repeat collection |"
        )

    lines.extend(
        [
            "",
            "## Observed and derived nodes",
            "",
            "| Space | State | Claim | Time | Metrics |",
            "|---|---|---|---|---|",
        ]
    )
    for item in graph.get("nodes", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {safe_text(item.get('space'))} | {safe_text(item.get('state'))} | "
            f"{safe_text(item.get('label'))} | {time_text(item.get('time_ms'))} | "
            f"{safe_text(item.get('metrics', {}))} |"
        )

    hypotheses = [
        item
        for item in graph.get("nodes", [])
        if isinstance(item, dict) and item.get("state") == "hypothesis"
    ]
    observed = [
        item
        for item in graph.get("nodes", [])
        if isinstance(item, dict) and item.get("state") == "observed"
    ]
    lines.extend(
        [
            "",
            "## Proven vs hypothesis",
            "",
            "**Observed in this report:** "
            + (
                ", ".join(str(item.get("label")) for item in observed)
                if observed
                else "none"
            )
            + ".",
            "",
            "**Explicit hypotheses:** "
            + (
                ", ".join(str(item.get("label")) for item in hypotheses)
                if hypotheses
                else "none; unsupported historical hypotheses were omitted"
            )
            + ".",
            "",
            "## Boundary",
            "",
            (
                "This is a single passive public-page Lighthouse run. Integrity is "
                "checked, but temporal stability, user impact, and security impact are "
                "not established automatically."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    graph = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.write_text(render(graph), encoding="utf-8")


if __name__ == "__main__":
    main()
