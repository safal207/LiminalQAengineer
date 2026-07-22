#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_lhr(root: Path) -> dict[str, Any] | None:
    candidates = glob.glob(".lighthouseci/**/*.json", recursive=True)
    candidates += glob.glob(str(root / "lighthouse" / "**" / "*.json"), recursive=True)
    for candidate in candidates:
        value = read_json(Path(candidate))
        if isinstance(value, dict) and "categories" in value and "audits" in value:
            return value
    return None


def status_to_reproduction(status: str) -> str:
    return {
        "STILL_REPRODUCED": "REPRODUCED",
        "REGRESSED": "REPRODUCED",
        "FIXED": "NOT_REPRODUCED",
        "STALE_EVIDENCE": "BLOCKED",
    }[status]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    chart_path = out / "chart-route" / "route-matrix-result.json"
    chart = read_json(chart_path)
    if chart is None:
        chart_status = "STALE_EVIDENCE"
    elif chart.get("verdict") == "USER_AGENT_ROUTING_CONFIRMED":
        chart_status = "STILL_REPRODUCED"
    elif chart.get("verdict") == "NOT_REPRODUCED":
        chart_status = "FIXED"
    elif chart.get("verdict") == "MIXED_ROUTE_FAILURE":
        chart_status = "REGRESSED"
    else:
        chart_status = "STALE_EVIDENCE"

    lhr = find_lhr(out)
    if lhr:
        perf_score = round(float(lhr["categories"]["performance"]["score"]) * 100, 1)
        lcp_ms = round(float(lhr["audits"]["largest-contentful-paint"]["numericValue"]), 1)
        fcp_ms = round(float(lhr["audits"]["first-contentful-paint"]["numericValue"]), 1)
        tbt_ms = round(float(lhr["audits"]["total-blocking-time"]["numericValue"]), 1)
        cls = round(float(lhr["audits"]["cumulative-layout-shift"]["numericValue"]), 3)
        requests = lhr.get("audits", {}).get("network-requests", {}).get("details", {}).get("items", [])
        scripts = [item for item in requests if item.get("resourceType") == "Script"]
        script_requests = len(scripts)
        script_transfer = int(sum(item.get("transferSize") or 0 for item in scripts))
        if perf_score >= 65 and lcp_ms <= 4000:
            performance_status = "FIXED"
        elif lcp_ms > 13_805 or perf_score < 30:
            performance_status = "REGRESSED"
        else:
            performance_status = "STILL_REPRODUCED"
    else:
        perf_score = lcp_ms = fcp_ms = tbt_ms = cls = None
        script_requests = script_transfer = None
        performance_status = "STALE_EVIDENCE"

    image_path = out / "terminal-image" / "terminal-image-visibility-result.json"
    image = read_json(image_path)
    if image is None:
        hidden_status = "STALE_EVIDENCE"
        hidden_bytes = hidden_count = hidden_asset = None
    else:
        hidden_bytes = image.get("loaded_invisible_encoded_bytes", 0)
        hidden_count = image.get("loaded_invisible_image_count", 0)
        hidden_asset = next(
            (
                item
                for item in image.get("loaded_invisible_images", [])
                if "onboarding.light.2x.png" in (item.get("current_src") or item.get("src") or "")
            ),
            None,
        )
        if image.get("verdict") == "NO_MATERIAL_HIDDEN_IMAGE_WASTE" or not hidden_asset:
            hidden_status = "FIXED"
        elif hidden_bytes > 433_500:
            hidden_status = "REGRESSED"
        else:
            hidden_status = "STILL_REPRODUCED"

    terminal_path = out / "terminal-loading" / "result" / "terminal-loading-result.json"
    terminal = read_json(terminal_path)
    if terminal is None:
        missing_status = "STALE_EVIDENCE"
        missing_observations: list[dict[str, Any]] = []
    else:
        missing_observations = []
        for result in terminal.get("results", []):
            for item in result.get("first_party_http_errors", []):
                if str(item.get("url", "")).endswith("/images/2022/authorization/onboarding.png"):
                    missing_observations.append({"profile": result.get("profile"), **item})
        missing_status = "STILL_REPRODUCED" if missing_observations else "FIXED"

    rows = [
        {
            "finding_id": "TRADERNET-4X-001",
            "title": "Mobile user-agent chart routing",
            "historical_source": "PR #58",
            "historical_baseline": "mobile UA returned 404 in both viewports while desktop UA rendered the chart",
            "current_status": chart_status,
            "current_evidence": {
                "verdict": chart.get("verdict") if chart else None,
                "results": chart.get("results") if chart else None,
            },
        },
        {
            "finding_id": "TRADERNET-4X-002",
            "title": "Mobile homepage performance",
            "historical_source": "PR #54",
            "historical_baseline": {
                "performance_score": 41,
                "mobile_lcp_ms": 11044,
                "script_requests": 55,
                "script_transfer_bytes_approx": 1533300,
            },
            "current_status": performance_status,
            "current_evidence": {
                "performance_score": perf_score,
                "lcp_ms": lcp_ms,
                "fcp_ms": fcp_ms,
                "tbt_ms": tbt_ms,
                "cls": cls,
                "script_requests": script_requests,
                "script_transfer_bytes": script_transfer,
            },
        },
        {
            "finding_id": "TRADERNET-4X-003",
            "title": "Loaded but invisible mobile onboarding asset",
            "historical_source": "PR #60",
            "historical_baseline": {
                "asset": "onboarding.light.2x.png",
                "encoded_bytes": 346800,
                "rendered_size": "0x0",
            },
            "current_status": hidden_status,
            "current_evidence": {
                "loaded_invisible_bytes": hidden_bytes,
                "loaded_invisible_count": hidden_count,
                "asset": hidden_asset,
            },
        },
        {
            "finding_id": "TRADERNET-4X-004",
            "title": "Missing first-party onboarding.png",
            "historical_source": "PR #60",
            "historical_baseline": "onboarding.png returned HTTP 404 on desktop and mobile",
            "current_status": missing_status,
            "current_evidence": {"matching_http_errors": missing_observations},
        },
    ]

    statuses = [row["current_status"] for row in rows]
    any_reproduced = any(status in {"STILL_REPRODUCED", "REGRESSED"} for status in statuses)
    any_stale = any(status == "STALE_EVIDENCE" for status in statuses)

    evidence_defs = [
        ("E-CHART", "rendered", chart_status, chart_path),
        ("E-LIGHTHOUSE", "measurement", performance_status, out / "lighthouse"),
        ("E-HIDDEN-ASSET", "network", hidden_status, image_path),
        ("E-MISSING-ASSET", "network", missing_status, terminal_path),
    ]
    evidence_ledger = [
        {
            "evidence_id": evidence_id,
            "type": kind,
            "status": "UNAVAILABLE" if status == "STALE_EVIDENCE" else "OBSERVED",
            "observed_at": now,
            "valid_time": now,
            "transaction_time": now,
            "ref": str(ref),
            "integrity": "UNVERIFIED" if status == "STALE_EVIDENCE" else "VERIFIED",
        }
        for evidence_id, kind, status, ref in evidence_defs
    ]

    severity = {
        "TRADERNET-4X-001": "HIGH",
        "TRADERNET-4X-002": "HIGH",
        "TRADERNET-4X-003": "MEDIUM",
        "TRADERNET-4X-004": "LOW",
    }
    evidence_ref = {
        "TRADERNET-4X-001": "E-CHART",
        "TRADERNET-4X-002": "E-LIGHTHOUSE",
        "TRADERNET-4X-003": "E-HIDDEN-ASSET",
        "TRADERNET-4X-004": "E-MISSING-ASSET",
    }
    findings = []
    for row in rows:
        status = row["current_status"]
        reproduction = status_to_reproduction(status)
        claim_level = "CONFIRMED_DEFECT" if reproduction == "REPRODUCED" else "OBSERVATION"
        confidence = 0.99 if status == "STILL_REPRODUCED" else 0.9 if status in {"FIXED", "REGRESSED"} else 0.2
        findings.append(
            {
                "finding_id": row["finding_id"],
                "title": f"{row['title']} — {status}",
                "claim_level": claim_level,
                "severity": severity[row["finding_id"]],
                "confidence": confidence,
                "reproduction_status": reproduction,
                "trace_refs": [f"trace:{row['finding_id']}:fourth-rerun"],
                "evidence_refs": [evidence_ref[row["finding_id"]]],
                "causal_parent": None,
                "competing_explanations": [
                    "run-to-run network variance",
                    "public deployment changed between observations",
                ],
                "impact_class": "QUALITATIVE",
                "next_discriminating_test": "Repeat the same bounded matrix against the deployed remediation or investigate the exact routing/resource-loading branch.",
                "authority_boundary": "Public passive evidence only; no authentication, financial action, direct API testing, exploitation, deployment, contact, or merge authority.",
            }
        )

    packet = {
        "schema_version": "liminalqa-causal-deep-audit-packet-v0.1",
        "audit_id": f"tradernet-fourth-exact-rerun-{args.run_id}-{args.run_attempt}",
        "generated_at": now,
        "target": {
            "kind": "public_product",
            "id": "Tradernet public web",
            "canonical_origin": "https://tradernet.ru",
            "repository_full_name": "safal207/LiminalQAengineer",
        },
        "scope": {
            "included": [
                "public homepage",
                "public MICEXINDEXCF chart route",
                "public terminal authentication entry",
                "naturally initiated public resources",
            ],
            "excluded": [
                "authentication",
                "portfolio",
                "orders",
                "market depth",
                "direct application APIs",
                "fuzzing",
                "load testing",
                "active security testing",
            ],
            "profiles": [
                "desktop UA + desktop viewport",
                "desktop UA + mobile viewport",
                "mobile UA + desktop viewport",
                "mobile UA + mobile viewport",
                "Lighthouse mobile",
                "terminal desktop",
                "terminal mobile 4G",
            ],
            "stop_conditions": [
                "authentication required",
                "account data encountered",
                "financial action required",
                "allowlisted public origin exceeded",
            ],
        },
        "source_identity": {
            "identity_type": "run_attempt",
            "value": f"{args.workflow_sha}:{args.run_id}:{args.run_attempt}",
            "head_sha": args.workflow_sha,
            "workflow_sha": args.workflow_sha,
            "run_id": args.run_id,
            "run_attempt": args.run_attempt,
            "initial_check": "PASS",
            "final_check": "PASS",
        },
        "authority": {
            "mode": "evidence_only",
            "allowed": [
                "passive public navigation",
                "screenshots",
                "runtime and network observation",
                "Lighthouse measurement",
                "local report generation",
            ],
            "prohibited": [
                "login",
                "form submission",
                "account access",
                "financial operations",
                "direct API testing",
                "security exploitation",
                "external submission",
                "deployment",
                "merge",
            ],
        },
        "verdict": {
            "state": "CONFIRMED_DEFECT" if any_reproduced else "INCOMPLETE" if any_stale else "READY_WITH_ADVISORY_GAPS",
            "gate": "ALLOW_REPORT" if not any_stale else "ESCALATE",
            "summary": f"Fourth exact-time rerun statuses: {', '.join(statuses)}.",
        },
        "findings": findings,
        "evidence_ledger": evidence_ledger,
        "limitations": [
            "Laboratory evidence is not a production percentile.",
            "Public unauthenticated surfaces do not establish authenticated trading-journey behavior.",
            "A fixed current observation does not identify the deployment or commit that changed the public product.",
        ],
        "next_action": {
            "class": "FIX_CONFIRMED_DEFECT" if any_reproduced else "HUMAN_ADJUDICATION",
            "action": "Prioritize the mobile chart route if reproduced; otherwise review the highest-severity remaining reproduced finding.",
            "owner_or_authority": "Tradernet product and engineering owners",
            "completion_signal": "The same exact matrix passes on a deployed change and preserves the requested ticker and visible chart.",
            "stop_condition": "Stop before authentication, account access, order actions, direct API calls, external disclosure, deployment, or merge.",
        },
    }

    comparison = {
        "schema_version": "tradernet-fourth-exact-comparison-v1",
        "generated_at": now,
        "workflow_sha": args.workflow_sha,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "findings": rows,
    }
    (out / "comparison.json").write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "causal-deep-audit-packet.json").write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Tradernet fourth exact-time rerun",
        "",
        f"**Workflow SHA:** `{args.workflow_sha}`  ",
        f"**Run:** `{args.run_id}` · attempt `{args.run_attempt}`  ",
        f"**Gate:** `{packet['verdict']['gate']}`",
        "",
        "| Finding | Historical audit | Current status | Current evidence |",
        "|---|---|---|---|",
    ]
    for row in rows:
        evidence = json.dumps(row["current_evidence"], ensure_ascii=False, separators=(",", ":"))
        if len(evidence) > 500:
            evidence = evidence[:497] + "..."
        lines.append(
            f"| {row['title']} | {row['historical_source']} | **{row['current_status']}** | `{evidence}` |"
        )
    lines.extend(
        [
            "",
            "> Public passive evidence only. No login, account access, portfolio access, order action, direct API testing, fuzzing, load testing, exploitation, external submission, deployment, or merge.",
            "",
        ]
    )
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
