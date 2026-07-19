#!/usr/bin/env python3
"""Build a bounded, evidence-derived space-time causal graph from one Lighthouse report."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

THRESHOLDS = {
    "performance": 65,
    "accessibility": 85,
    "best-practices": 85,
    "seo": 85,
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def find_report(folder: Path) -> tuple[Path, dict[str, Any]]:
    for pattern in ("lhr-*.json", "*.report.json", "*.json"):
        for path in sorted(folder.glob(pattern)):
            try:
                report = load_json(path)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if isinstance(report.get("audits"), dict) and isinstance(
                report.get("categories"), dict
            ):
                return path, report
    raise FileNotFoundError("No Lighthouse report found")


def audit(report: dict[str, Any], audit_id: str) -> dict[str, Any]:
    value = report.get("audits", {}).get(audit_id, {})
    return value if isinstance(value, dict) else {}


def rows(report: dict[str, Any], audit_id: str) -> list[dict[str, Any]]:
    details = audit(report, audit_id).get("details", {})
    items = details.get("items", []) if isinstance(details, dict) else []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def numeric_audit(report: dict[str, Any], audit_id: str) -> float | None:
    value = audit(report, audit_id).get("numericValue")
    return round(float(value), 3) if isinstance(value, (int, float)) else None


def numeric(value: Any, digits: int = 1) -> float | None:
    return round(float(value), digits) if isinstance(value, (int, float)) else None


def request(report: dict[str, Any], predicate) -> dict[str, Any] | None:
    return next(
        (item for item in rows(report, "network-requests") if predicate(item)),
        None,
    )


def request_time(item: dict[str, Any] | None, key: str) -> float | None:
    return numeric(item.get(key) if item else None)


def nested_rows(report: dict[str, Any], audit_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in rows(report, audit_id):
        items = block.get("items")
        if block.get("type") == "table" and isinstance(items, list):
            result.extend(item for item in items if isinstance(item, dict))
    return result


def lcp_phases(report: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in nested_rows(report, "lcp-phases-insight"):
        name = item.get("phase")
        value = item.get("duration")
        if isinstance(name, str) and isinstance(value, (int, float)):
            result[name] = round(float(value), 1)
    return result


def lcp_checks(report: dict[str, Any]) -> dict[str, bool]:
    checklist = next(
        (
            item
            for item in rows(report, "lcp-discovery-insight")
            if item.get("type") == "checklist"
        ),
        {},
    )
    raw = checklist.get("items", {}) if isinstance(checklist, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: bool(value.get("value"))
        for key, value in raw.items()
        if isinstance(value, dict)
    }


def category_score(report: dict[str, Any], category_id: str) -> int | None:
    category = report.get("categories", {}).get(category_id)
    if not isinstance(category, dict):
        return None
    value = category.get("score")
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) * 100)


def resource_summary(report: dict[str, Any]) -> dict[str, dict[str, float | int | None]]:
    result: dict[str, dict[str, float | int | None]] = {}
    for item in rows(report, "resource-summary"):
        kind = item.get("resourceType")
        if not isinstance(kind, str):
            continue
        transfer = item.get("transferSize")
        result[kind] = {
            "requests": item.get("requestCount")
            if isinstance(item.get("requestCount"), int)
            else None,
            "transfer_kib": round(float(transfer) / 1024, 1)
            if isinstance(transfer, (int, float))
            else None,
        }
    return result


def unused_javascript(report: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in rows(report, "unused-javascript"):
        total = item.get("totalBytes")
        wasted = item.get("wastedBytes")
        if not isinstance(total, (int, float)) or not isinstance(wasted, (int, float)):
            continue
        result.append(
            {
                "url": item.get("url"),
                "wasted_kib": round(float(wasted) / 1024, 1),
                "wasted_percent": round(100 * float(wasted) / float(total), 1)
                if total
                else 0.0,
            }
        )
    return sorted(result, key=lambda item: item["wasted_kib"], reverse=True)[:8]


def console_error(report: dict[str, Any]) -> str | None:
    for item in rows(report, "errors-in-console"):
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    return None


def contrast_failures(report: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in rows(report, "color-contrast"):
        node = item.get("node")
        if isinstance(node, dict):
            result.append(
                {
                    "label": node.get("nodeLabel"),
                    "selector": node.get("selector"),
                    "explanation": node.get("explanation"),
                }
            )
    return result


def layout_shifts(report: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in rows(report, "layout-shifts"):
        result.append(
            {
                "score": numeric(item.get("score"), 4),
                "causes": item.get("subItems", {}).get("items", [])
                if isinstance(item.get("subItems"), dict)
                else [],
            }
        )
    return result


def add_node(
    nodes: list[dict[str, Any]],
    *,
    node_id: str,
    space: str,
    state: str,
    label: str,
    time_ms: Any = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    node = {
        "id": node_id,
        "space": space,
        "state": state,
        "label": label,
    }
    if time_ms is not None:
        node["time_ms"] = time_ms
    if metrics:
        node["metrics"] = metrics
    nodes.append(node)


def build(report_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    final_url = str(report.get("finalUrl") or report.get("requestedUrl") or "")
    origin = ""
    try:
        origin = final_url.split("/", 3)[0] + "//" + final_url.split("/", 3)[2]
    except IndexError:
        origin = ""

    root = request(report, lambda item: item.get("url") == final_url)
    if root is None and origin:
        root = request(report, lambda item: str(item.get("url", "")).startswith(origin))
    document = request(
        report,
        lambda item: item.get("mimeType") == "text/html"
        and item.get("statusCode") == 200,
    )
    mobile_hero = request(
        report, lambda item: "hero.mobile" in str(item.get("url", ""))
    )
    desktop_hero = request(
        report,
        lambda item: "/hero.light" in str(item.get("url", ""))
        and "hero.mobile" not in str(item.get("url", "")),
    )
    font = request(report, lambda item: str(item.get("url", "")).endswith(".woff2"))

    debug_data = audit(report, "document-latency-insight").get("details", {})
    debug_data = (
        debug_data.get("debugData", {}) if isinstance(debug_data, dict) else {}
    )
    if not isinstance(debug_data, dict):
        debug_data = {}

    redirect_observed = numeric(debug_data.get("redirectDuration"))
    redirect_savings = numeric_audit(report, "redirects")
    css_savings = numeric_audit(report, "render-blocking-resources")
    main_thread_ms = numeric_audit(report, "mainthread-work-breakdown")
    js_execution_ms = numeric_audit(report, "bootup-time")
    lcp_ms = numeric_audit(report, "largest-contentful-paint")
    fcp_ms = numeric_audit(report, "first-contentful-paint")
    cls = numeric_audit(report, "cumulative-layout-shift")
    phases = lcp_phases(report)
    checks = lcp_checks(report)
    resources = resource_summary(report)
    scripts = resources.get("script", {})
    top_unused = unused_javascript(report)
    unused_kib = round(sum(item["wasted_kib"] for item in top_unused), 1)
    error = console_error(report)
    contrast = contrast_failures(report)
    shifts = layout_shifts(report)

    scores = {
        category_id: category_score(report, category_id)
        for category_id in THRESHOLDS
    }
    known_scores = {
        category_id: score for category_id, score in scores.items() if score is not None
    }
    failed = [
        category_id
        for category_id, score in known_scores.items()
        if score < THRESHOLDS[category_id]
    ]
    verdict = "WARN" if failed or len(known_scores) != len(THRESHOLDS) else "PASS"

    nodes: list[dict[str, Any]] = []
    add_node(
        nodes,
        node_id="navigation",
        space="user",
        state="observed",
        label="Public navigation",
        time_ms=0,
    )

    if redirect_observed is not None or (redirect_savings or 0) > 0:
        add_node(
            nodes,
            node_id="redirect",
            space="edge",
            state="observed",
            label="Redirect chain",
            time_ms={
                "start": request_time(root, "networkRequestTime"),
                "end": request_time(root, "networkEndTime"),
            },
            metrics={
                "observed_ms": redirect_observed,
                "modelled_savings_ms": redirect_savings,
            },
        )

    if document:
        add_node(
            nodes,
            node_id="document",
            space="origin",
            state="observed",
            label="Final HTML response",
            time_ms={
                "start": request_time(document, "networkRequestTime"),
                "end": request_time(document, "networkEndTime"),
            },
            metrics={
                "server_response_ms": numeric_audit(report, "server-response-time")
            },
        )

    if css_savings is not None:
        add_node(
            nodes,
            node_id="css",
            space="document_head",
            state="derived",
            label="Render-blocking resources",
            metrics={"modelled_savings_ms": css_savings},
        )

    if main_thread_ms is not None or js_execution_ms is not None:
        add_node(
            nodes,
            node_id="runtime",
            space="main_thread",
            state="observed",
            label="Main-thread application work",
            metrics={
                "main_thread_ms": main_thread_ms,
                "js_execution_ms": js_execution_ms,
            },
        )

    discoverable = checks.get("requestDiscoverable")
    priority_hinted = checks.get("priorityHinted")
    discovery_delay = phases.get("resourceLoadDelay")
    if checks or discovery_delay is not None:
        label = (
            "LCP resource not initially discoverable"
            if discoverable is False
            else "LCP discovery evidence"
        )
        add_node(
            nodes,
            node_id="lcp_discovery",
            space="document_to_media",
            state="observed",
            label=label,
            time_ms=request_time(desktop_hero or mobile_hero, "networkRequestTime"),
            metrics={
                "discoverable": discoverable,
                "fetchpriority_high": priority_hinted,
                "resource_load_delay_ms": discovery_delay,
            },
        )

    transferred_heroes = [
        item
        for item in (mobile_hero, desktop_hero)
        if isinstance(item, dict)
    ]
    if transferred_heroes:
        add_node(
            nodes,
            node_id="hero_transfer",
            space="responsive_media",
            state="observed",
            label=(
                "Multiple hero variants transferred"
                if len(transferred_heroes) > 1
                else "Hero resource transferred"
            ),
            time_ms={
                "mobile": request_time(mobile_hero, "networkRequestTime"),
                "desktop": request_time(desktop_hero, "networkRequestTime"),
            },
            metrics={
                "resources": [item.get("url") for item in transferred_heroes],
                "count": len(transferred_heroes),
            },
        )

    if lcp_ms is not None:
        lcp_node = next(
            (
                item
                for item in rows(report, "lcp-phases-insight")
                if item.get("type") == "node"
            ),
            {},
        )
        add_node(
            nodes,
            node_id="lcp",
            space="above_fold",
            state="observed",
            label="Largest Contentful Paint",
            time_ms=lcp_ms,
            metrics={
                "lcp_ms": lcp_ms,
                "fcp_ms": fcp_ms,
                "element": lcp_node.get("nodeLabel"),
                "selector": lcp_node.get("selector"),
            },
        )

    if scripts or top_unused:
        add_node(
            nodes,
            node_id="javascript",
            space="network_runtime",
            state="observed",
            label="JavaScript delivery",
            metrics={
                "requests": scripts.get("requests"),
                "transfer_kib": scripts.get("transfer_kib"),
                "top_unused": top_unused,
                "top_unused_total_kib": unused_kib,
            },
        )

    if error:
        add_node(
            nodes,
            node_id="console_error",
            space="document_runtime",
            state="observed",
            label="Console error observed",
            metrics={"description": error},
        )

    if cls is not None or shifts:
        add_node(
            nodes,
            node_id="layout",
            space="viewport",
            state="observed",
            label="Layout stability",
            time_ms=request_time(font, "networkRequestTime"),
            metrics={"cls": cls, "shifts": shifts},
        )

    if contrast:
        add_node(
            nodes,
            node_id="contrast",
            space="above_fold",
            state="observed",
            label="Contrast failures",
            time_ms=fcp_ms,
            metrics={"elements": contrast, "count": len(contrast)},
        )

    add_node(
        nodes,
        node_id="decision",
        space="quality_gate",
        state="derived",
        label=f"LiminalQA {verdict}",
        time_ms=lcp_ms,
        metrics={
            "verdict": verdict,
            "scores": scores,
            "thresholds": THRESHOLDS,
            "failed_categories": failed,
        },
    )

    node_ids = {node["id"] for node in nodes}
    candidate_edges = [
        ("navigation", "redirect", "triggers", "observed"),
        ("navigation", "document", "requests", "observed"),
        ("redirect", "document", "delays", "observed"),
        ("document", "css", "discovers", "observed"),
        ("document", "runtime", "starts", "observed"),
        ("runtime", "lcp_discovery", "may_delay", "derived"),
        ("lcp_discovery", "lcp", "contributes_to", "derived"),
        ("hero_transfer", "lcp", "supplies_resource", "observed"),
        ("css", "lcp", "may_delay_render", "derived"),
        ("javascript", "decision", "affects_performance", "derived"),
        ("console_error", "decision", "affects_best_practices", "derived"),
        ("layout", "decision", "affects_stability", "derived"),
        ("contrast", "decision", "affects_accessibility", "derived"),
        ("lcp", "decision", "affects_performance", "derived"),
    ]
    edges = [
        {"from": left, "to": right, "relation": relation, "state": state}
        for left, right, relation, state in candidate_edges
        if left in node_ids and right in node_ids
    ]

    ranked: list[dict[str, Any]] = []

    def rank_candidate(
        impact: float,
        cause: str,
        status: str,
        why: str,
        next_test: str,
    ) -> None:
        ranked.append(
            {
                "_impact": impact,
                "cause": cause,
                "status": status,
                "why": why,
                "next_test": next_test,
            }
        )

    if discoverable is False or (discovery_delay or 0) > 0:
        rank_candidate(
            float(discovery_delay or 0),
            "LCP discovery delay",
            "OBSERVED",
            (
                f"Discoverable={discoverable}; fetchpriority_high={priority_hinted}; "
                f"resource-load delay={discovery_delay} ms."
            ),
            "Expose the exact observed LCP resource in initial HTML and repeat the run.",
        )
    if scripts or top_unused:
        rank_candidate(
            float(scripts.get("transfer_kib") or 0),
            "JavaScript delivery",
            "OBSERVED",
            (
                f"{scripts.get('requests')} requests, {scripts.get('transfer_kib')} KiB "
                f"transferred; top unused entries total {unused_kib} KiB."
            ),
            "Compare with a landing-only bundle and repeat under the same profile.",
        )
    if redirect_observed is not None or (redirect_savings or 0) > 0:
        rank_candidate(
            float(redirect_observed or redirect_savings or 0),
            "Redirect chain",
            "OBSERVED",
            (
                f"Observed redirect duration={redirect_observed} ms; "
                f"modelled savings={redirect_savings} ms."
            ),
            "Compare the requested URL with the final canonical URL on the same runner.",
        )
    if len(transferred_heroes) > 1:
        rank_candidate(
            float(len(transferred_heroes)),
            "Responsive hero overdelivery",
            "OBSERVED",
            f"{len(transferred_heroes)} distinct hero resources transferred in this run.",
            "Trace DOM/resource initiators before claiming reconciliation or replacement.",
        )
    if css_savings is not None and css_savings > 0:
        rank_candidate(
            float(css_savings),
            "Render-blocking resources",
            "MODELLED",
            f"Lighthouse modelled {css_savings} ms potential savings.",
            "Test critical CSS and deferred non-critical styles in a counterfactual.",
        )
    if cls is not None and cls > 0:
        rank_candidate(
            float(cls) * 1000,
            "Layout instability",
            "OBSERVED",
            f"CLS={cls}; {len(shifts)} shift records were captured.",
            "Add dimensions/aspect-ratio and repeat the same navigation.",
        )
    if error:
        rank_candidate(
            1.0,
            "Console error",
            "OBSERVED",
            error.replace("\n", " ")[:240],
            "Reproduce with source maps and verify visible user impact separately.",
        )

    ranked.sort(key=lambda item: item["_impact"], reverse=True)
    ranked_causes = [
        {
            "rank": index,
            "cause": item["cause"],
            "status": item["status"],
            "why": item["why"],
            "next_test": item["next_test"],
        }
        for index, item in enumerate(ranked, start=1)
    ]

    dominant_path = [
        node_id
        for node_id in (
            "navigation",
            "redirect",
            "document",
            "runtime",
            "lcp_discovery",
            "lcp",
            "decision",
        )
        if node_id in node_ids
    ]

    return {
        "schema_version": "liminalqa-space-time-causality-v2",
        "target": final_url,
        "guidance": (
            "Every observed or derived claim in this packet is computed from the "
            "current Lighthouse report; unsupported historical claims are omitted."
        ),
        "axes": {
            "space": sorted({node["space"] for node in nodes}),
            "valid_time": "navigation-relative milliseconds",
            "transaction_time": "Lighthouse fetch and graph generation",
            "note": "Observed data and modelled Lighthouse savings remain distinct.",
        },
        "run_count": 1,
        "evidence": {
            "file": report_path.name,
            "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "fetch_time": report.get("fetchTime"),
            "lighthouse_version": report.get("lighthouseVersion"),
        },
        "dominant_path": dominant_path,
        "nodes": nodes,
        "edges": edges,
        "ranked_causes": ranked_causes,
        "boundaries": {
            "active_security_testing": False,
            "authenticated_testing": False,
            "financial_operations": False,
            "vulnerability_claim": False,
            "temporal_stability_proven": False,
            "single_run_confidence": "LOW",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    report_path, report = find_report(args.input_dir)
    graph = build(report_path, report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "causality-graph.json"
    output.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "nodes": len(graph["nodes"])}, indent=2))


if __name__ == "__main__":
    main()
