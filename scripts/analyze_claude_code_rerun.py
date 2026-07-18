#!/usr/bin/env python3
"""Analyze an exact three-run Claude Code Lighthouse rerun without treating NO_LCP as score zero."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path
from typing import Any

TARGET = "https://claude.com/product/claude-code"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def audit_metric(report: dict[str, Any], audit_id: str) -> dict[str, Any]:
    audit = (report.get("audits") or {}).get(audit_id) or {}
    numeric = number(audit.get("numericValue"))
    error = audit.get("errorMessage") if isinstance(audit.get("errorMessage"), str) else None
    return {
        "numeric_value": numeric,
        "display_value": audit.get("displayValue"),
        "score": number(audit.get("score")),
        "score_display_mode": audit.get("scoreDisplayMode"),
        "error": error,
        "valid": numeric is not None and audit.get("scoreDisplayMode") != "error",
    }


def category_score(report: dict[str, Any], category: str) -> float | None:
    raw = number(((report.get("categories") or {}).get(category) or {}).get("score"))
    return None if raw is None else round(raw * 100, 2)


def analyze_report(path: Path, index: int) -> dict[str, Any]:
    report = load_json(path)
    requested = report.get("requestedUrl")
    final_url = report.get("finalDisplayedUrl") or report.get("finalUrl")
    if requested != TARGET:
        raise ValueError(f"run {index} requested unexpected URL {requested!r}")
    if final_url != TARGET:
        raise ValueError(f"run {index} ended at unexpected URL {final_url!r}")

    lcp = audit_metric(report, "largest-contentful-paint")
    tbt = audit_metric(report, "total-blocking-time")
    fcp = audit_metric(report, "first-contentful-paint")
    speed_index = audit_metric(report, "speed-index")
    diagnostics = ((((report.get("audits") or {}).get("diagnostics") or {}).get("details") or {}).get("items") or [{}])[0]
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    return {
        "run": index,
        "fetch_time": report.get("fetchTime"),
        "requested_url": requested,
        "final_url": final_url,
        "runtime_error": report.get("runtimeError"),
        "raw_report_sha256": sha256_file(path),
        "scores": {
            "performance": category_score(report, "performance"),
            "accessibility": category_score(report, "accessibility"),
            "best_practices": category_score(report, "best-practices"),
            "seo": category_score(report, "seo"),
        },
        "metrics": {
            "fcp_ms": fcp["numeric_value"],
            "lcp_ms": lcp["numeric_value"],
            "tbt_ms": tbt["numeric_value"],
            "speed_index_ms": speed_index["numeric_value"],
        },
        "measurement": {
            "lcp_valid": lcp["valid"],
            "lcp_error": lcp["error"],
            "tbt_valid": tbt["valid"],
            "tbt_error": tbt["error"],
        },
        "diagnostics": {
            "num_requests": diagnostics.get("numRequests"),
            "total_byte_weight": diagnostics.get("totalByteWeight"),
            "total_task_time_ms": diagnostics.get("totalTaskTime"),
            "tasks_over_50_ms": diagnostics.get("numTasksOver50ms"),
        },
    }


def median(values: list[float]) -> float | None:
    return None if not values else round(float(statistics.median(values)), 3)


def build_result(paths: list[Path]) -> dict[str, Any]:
    if len(paths) != 3:
        raise ValueError(f"exact rerun requires 3 Lighthouse reports; got {len(paths)}")
    runs = [analyze_report(path, index) for index, path in enumerate(paths, start=1)]
    valid = [run for run in runs if run["measurement"]["lcp_valid"]]
    no_lcp = [run for run in runs if run["measurement"]["lcp_error"] == "NO_LCP"]
    runtime_errors = [run for run in runs if run["runtime_error"]]

    if len(valid) >= 2:
        state = "VALID_LCP_REPEATED"
        prior_no_lcp_status = "NOT_REPRODUCED_UNDER_DEVTOOLS_PROFILE"
        claim_support = "observed"
    elif len(no_lcp) >= 2:
        state = "NO_LCP_REPEATED"
        prior_no_lcp_status = "REPRODUCED_UNDER_DEVTOOLS_PROFILE"
        claim_support = "observed"
    else:
        state = "MIXED_INCONCLUSIVE"
        prior_no_lcp_status = "INCONCLUSIVE"
        claim_support = "unknown"

    lcp_values = [run["metrics"]["lcp_ms"] for run in valid if run["metrics"]["lcp_ms"] is not None]
    tbt_values = [run["metrics"]["tbt_ms"] for run in valid if run["metrics"]["tbt_ms"] is not None]
    perf_values = [run["scores"]["performance"] for run in valid if run["scores"]["performance"] is not None]

    result = {
        "schema_version": "liminalqa-claude-code-exact-rerun-v0.1",
        "target": TARGET,
        "profile": {
            "runs": 3,
            "form_factor": "mobile",
            "viewport": "390x844",
            "device_scale_factor": 1,
            "throttling_method": "devtools",
            "rtt_ms": 150,
            "throughput_kbps": 1638.4,
            "cpu_slowdown_multiplier": 4,
            "cache": "fresh Lighthouse context per run",
            "interaction": "one passive navigation per run",
        },
        "provenance": {
            "repository": os.environ.get("GITHUB_REPOSITORY", "unknown"),
            "exact_head_sha": os.environ.get("GITHUB_SHA", "unknown"),
            "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "unknown"),
        },
        "prior_evidence": {
            "finding_id": "CLAUDE-CODE-PERFORMANCE-ZERO-001",
            "workflow_run_id": "29665084768",
            "raw_report_sha256": "b275a7c310867607546657a89b4c75d537c896277199d8e4abe70bc210857db3",
            "observed": "single Lighthouse simulated-throttling report emitted NO_LCP; Performance 0 was not treated as a product score",
        },
        "result": {
            "state": state,
            "claim_support": claim_support,
            "valid_lcp_runs": len(valid),
            "no_lcp_runs": len(no_lcp),
            "runtime_error_runs": len(runtime_errors),
            "prior_no_lcp_status": prior_no_lcp_status,
            "median_performance": median(perf_values),
            "median_lcp_ms": median(lcp_values),
            "median_tbt_ms": median(tbt_values),
            "lcp_range_ms": None if not lcp_values else [round(min(lcp_values), 3), round(max(lcp_values), 3)],
        },
        "runs": runs,
        "interpretation": {
            "performance_zero_is_product_score": False,
            "supersession_allowed": len(valid) >= 2,
            "boundary": "This experiment tests measurement reproducibility under one bounded lab profile; it is not field telemetry and does not prove one root cause.",
        },
    }
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["result_sha256"] = hashlib.sha256(canonical).hexdigest()
    return result


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["result"]
    lines = [
        "# Claude Code exact Lighthouse rerun v0.1",
        "",
        f"**State:** `{summary['state']}`  ",
        f"**Exact head:** `{result['provenance']['exact_head_sha']}`  ",
        f"**Workflow run:** `{result['provenance']['workflow_run_id']}`  ",
        f"**Result SHA-256:** `{result['result_sha256']}`",
        "",
        "## Reproducibility",
        "",
        f"- Valid LCP runs: **{summary['valid_lcp_runs']}/3**",
        f"- NO_LCP runs: **{summary['no_lcp_runs']}/3**",
        f"- Runtime-error runs: **{summary['runtime_error_runs']}/3**",
        f"- Prior NO_LCP status: `{summary['prior_no_lcp_status']}`",
        f"- Median Performance: `{summary['median_performance']}`",
        f"- Median LCP: `{summary['median_lcp_ms']} ms`",
        f"- Median TBT: `{summary['median_tbt_ms']} ms`",
        "",
        "## Runs",
        "",
        "| Run | Performance | FCP | LCP | TBT | LCP state | Raw SHA-256 |",
        "|---:|---:|---:|---:|---:|---|---|",
    ]
    for run in result["runs"]:
        metrics = run["metrics"]
        measurement = run["measurement"]
        state = "valid" if measurement["lcp_valid"] else measurement["lcp_error"] or "invalid"
        lines.append(
            f"| {run['run']} | {run['scores']['performance']} | {metrics['fcp_ms']} | "
            f"{metrics['lcp_ms']} | {metrics['tbt_ms']} | {state} | `{run['raw_report_sha256']}` |"
        )
    lines.extend([
        "",
        "## Evidence boundary",
        "",
        "> Performance `0` from a report with `NO_LCP` is not a valid product-performance score. Supersession is allowed only when at least two of three exact reruns produce valid LCP measurements.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.input_dir.glob("lhr-*.json"))
    result = build_result(paths)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "claude-code-exact-rerun-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "claude-code-exact-rerun-result.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    print(render_markdown(result))


if __name__ == "__main__":
    main()
