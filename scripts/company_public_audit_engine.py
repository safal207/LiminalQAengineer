#!/usr/bin/env python3
"""Validate, summarize, and aggregate self-service public company audits.

This engine is deliberately fail-closed. It accepts only allowlisted public HTTPS
pages and quality/accessibility observation settings. It has no schema fields for
credentials, cookies, custom headers, JavaScript injection, form submission,
direct application APIs, financial operations, fuzzing, or load testing.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA_VERSION = "liminalqa-company-public-audit-v1"
RESULT_SCHEMA_VERSION = "liminalqa-company-public-audit-result-v1"
LIGHTHOUSE_SCHEMA_VERSION = "liminalqa-company-lighthouse-summary-v1"
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
PROFILES = {"desktop", "mobile"}
SENSITIVE_QUERY_KEYS = re.compile(
    r"(?:token|secret|key|auth|session|password|passwd|credential|cookie|email|phone|account|user_id|userid)",
    re.IGNORECASE,
)
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,47}$")

REQUIRED_BOUNDARIES: dict[str, bool] = {
    "public_pages_only": True,
    "natural_navigation_only": True,
    "passive_browser_observation": True,
    "keyboard_navigation_only": True,
    "authenticated_testing": False,
    "account_access": False,
    "credentials_or_secrets": False,
    "direct_api_testing": False,
    "form_submission": False,
    "publishing": False,
    "financial_operations": False,
    "fuzzing": False,
    "load_testing": False,
    "active_security_testing": False,
    "server_state_change": False,
    "vulnerability_claim": False,
}

TOP_LEVEL_KEYS = {
    "schema_version",
    "company",
    "allowed_origins",
    "allowed_query_keys",
    "targets",
    "profiles",
    "settings",
    "category_thresholds",
    "boundaries",
    "notes",
}
COMPANY_KEYS = {"name", "audit_name"}
SETTINGS_KEYS = {
    "settle_ms",
    "keyboard_tab_steps",
    "lighthouse_runs",
    "max_parallel",
    "retain_body_sample",
}
TARGET_KEYS = {"id", "url", "kind"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise ValueError(f"Unsupported {label} keys: {', '.join(extra)}")


def require_string(value: Any, label: str, minimum: int = 1, maximum: int = 200) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = value.strip()
    if not minimum <= len(normalized) <= maximum:
        raise ValueError(f"{label} length must be between {minimum} and {maximum}")
    return normalized


def reject_non_public_hostname(hostname: str) -> None:
    lowered = hostname.lower().rstrip(".")
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".local"):
        raise ValueError(f"Local hostname is not allowed: {hostname}")
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError(f"Non-public IP target is not allowed: {hostname}")


def normalize_origin(raw_origin: str) -> str:
    parsed = urlsplit(require_string(raw_origin, "allowed origin", 8, 300))
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS origins are allowed")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Credentials and custom ports are not allowed in origins")
    if not parsed.hostname:
        raise ValueError("Origin hostname is required")
    reject_non_public_hostname(parsed.hostname)
    if parsed.query or parsed.fragment:
        raise ValueError("Origin query strings and fragments are not allowed")
    if parsed.path not in {"", "/"}:
        raise ValueError("allowed_origins must contain origins, not paths")
    return f"https://{parsed.hostname.lower()}"


def normalize_target_url(
    raw_url: str,
    allowed_origins: set[str],
    allowed_query_keys: set[str],
) -> str:
    parsed = urlsplit(require_string(raw_url, "target URL", 8, 2000))
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS target URLs are allowed")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Credentials and custom ports are not allowed in targets")
    if not parsed.hostname:
        raise ValueError("Target hostname is required")
    reject_non_public_hostname(parsed.hostname)
    if parsed.fragment:
        raise ValueError("URL fragments are not allowed")
    origin = f"https://{parsed.hostname.lower()}"
    if origin not in allowed_origins:
        raise ValueError(f"Target origin is outside allowed_origins: {origin}")

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_pairs: list[tuple[str, str]] = []
    if len(query_pairs) > 8:
        raise ValueError("A target may contain at most 8 query parameters")
    for key, value in query_pairs:
        if key not in allowed_query_keys:
            raise ValueError(f"Query key is not allowlisted: {key}")
        if SENSITIVE_QUERY_KEYS.search(key):
            raise ValueError(f"Sensitive-looking query key is forbidden: {key}")
        if len(value) > 200:
            raise ValueError(f"Query value for {key} is too long")
        normalized_pairs.append((key, value))

    path = parsed.path or "/"
    if not path.startswith("/") or len(path) > 1000:
        raise ValueError("Target path is invalid")
    return urlunsplit(("https", parsed.hostname.lower(), path, urlencode(normalized_pairs, doseq=True), ""))


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    require_exact_keys(raw, TOP_LEVEL_KEYS, "top-level")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {SCHEMA_VERSION}")

    company = raw.get("company")
    if not isinstance(company, dict):
        raise ValueError("company must be an object")
    require_exact_keys(company, COMPANY_KEYS, "company")
    normalized_company = {
        "name": require_string(company.get("name"), "company.name", 1, 120),
        "audit_name": require_string(company.get("audit_name"), "company.audit_name", 1, 160),
    }

    origins_raw = raw.get("allowed_origins")
    if not isinstance(origins_raw, list) or not 1 <= len(origins_raw) <= 8:
        raise ValueError("allowed_origins must contain 1 to 8 origins")
    origins = [normalize_origin(value) for value in origins_raw]
    if len(origins) != len(set(origins)):
        raise ValueError("allowed_origins must be unique")
    origin_set = set(origins)

    query_keys_raw = raw.get("allowed_query_keys")
    if not isinstance(query_keys_raw, list) or len(query_keys_raw) > 20:
        raise ValueError("allowed_query_keys must be a list with at most 20 entries")
    query_keys: list[str] = []
    for value in query_keys_raw:
        key = require_string(value, "allowed query key", 1, 64)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
            raise ValueError(f"Invalid query key: {key}")
        if SENSITIVE_QUERY_KEYS.search(key):
            raise ValueError(f"Sensitive-looking query key is forbidden: {key}")
        query_keys.append(key)
    if len(query_keys) != len(set(query_keys)):
        raise ValueError("allowed_query_keys must be unique")
    query_key_set = set(query_keys)

    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list) or not 1 <= len(targets_raw) <= 8:
        raise ValueError("targets must contain 1 to 8 public pages")
    targets: list[dict[str, str]] = []
    target_ids: set[str] = set()
    for index, target in enumerate(targets_raw):
        if not isinstance(target, dict):
            raise ValueError(f"targets[{index}] must be an object")
        require_exact_keys(target, TARGET_KEYS, f"targets[{index}]")
        target_id = require_string(target.get("id"), f"targets[{index}].id", 1, 48)
        if not ID_PATTERN.fullmatch(target_id):
            raise ValueError(f"Invalid target id: {target_id}")
        if target_id in target_ids:
            raise ValueError(f"Duplicate target id: {target_id}")
        target_ids.add(target_id)
        kind = require_string(target.get("kind"), f"targets[{index}].kind", 1, 48)
        if not KIND_PATTERN.fullmatch(kind):
            raise ValueError(f"Invalid target kind: {kind}")
        targets.append(
            {
                "id": target_id,
                "url": normalize_target_url(target.get("url"), origin_set, query_key_set),
                "kind": kind,
            }
        )

    profiles_raw = raw.get("profiles")
    if not isinstance(profiles_raw, list) or not 1 <= len(profiles_raw) <= 2:
        raise ValueError("profiles must contain desktop, mobile, or both")
    profiles = [require_string(value, "profile", 1, 20) for value in profiles_raw]
    if len(profiles) != len(set(profiles)) or not set(profiles).issubset(PROFILES):
        raise ValueError("profiles must be unique values from: desktop, mobile")

    settings = raw.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    require_exact_keys(settings, SETTINGS_KEYS, "settings")
    settle_ms = settings.get("settle_ms")
    keyboard_steps = settings.get("keyboard_tab_steps")
    lighthouse_runs = settings.get("lighthouse_runs")
    max_parallel = settings.get("max_parallel")
    retain_body_sample = settings.get("retain_body_sample")
    if not isinstance(settle_ms, int) or not 0 <= settle_ms <= 15000:
        raise ValueError("settings.settle_ms must be an integer from 0 to 15000")
    if not isinstance(keyboard_steps, int) or not 0 <= keyboard_steps <= 40:
        raise ValueError("settings.keyboard_tab_steps must be an integer from 0 to 40")
    if not isinstance(lighthouse_runs, int) or not 1 <= lighthouse_runs <= 3:
        raise ValueError("settings.lighthouse_runs must be an integer from 1 to 3")
    if not isinstance(max_parallel, int) or not 1 <= max_parallel <= 4:
        raise ValueError("settings.max_parallel must be an integer from 1 to 4")
    if not isinstance(retain_body_sample, bool):
        raise ValueError("settings.retain_body_sample must be boolean")

    thresholds_raw = raw.get("category_thresholds")
    if not isinstance(thresholds_raw, dict) or set(thresholds_raw) != set(CATEGORIES):
        raise ValueError(f"category_thresholds must contain exactly: {', '.join(CATEGORIES)}")
    thresholds: dict[str, float] = {}
    for category in CATEGORIES:
        value = thresholds_raw.get(category)
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise ValueError(f"Threshold for {category} must be between 0 and 1")
        thresholds[category] = round(float(value), 3)

    boundaries = raw.get("boundaries")
    if not isinstance(boundaries, dict):
        raise ValueError("boundaries must be an object")
    if set(boundaries) != set(REQUIRED_BOUNDARIES):
        missing = sorted(set(REQUIRED_BOUNDARIES) - set(boundaries))
        extra = sorted(set(boundaries) - set(REQUIRED_BOUNDARIES))
        raise ValueError(f"Boundary keys mismatch; missing={missing}, extra={extra}")
    for key, expected in REQUIRED_BOUNDARIES.items():
        if boundaries.get(key) is not expected:
            raise ValueError(f"Boundary {key} must be {str(expected).lower()}")

    notes_raw = raw.get("notes")
    if not isinstance(notes_raw, list) or len(notes_raw) > 20:
        raise ValueError("notes must be a list with at most 20 entries")
    notes = [require_string(value, "note", 1, 500) for value in notes_raw]

    return {
        "schema_version": SCHEMA_VERSION,
        "company": normalized_company,
        "allowed_origins": origins,
        "allowed_query_keys": query_keys,
        "targets": targets,
        "profiles": profiles,
        "settings": {
            "settle_ms": settle_ms,
            "keyboard_tab_steps": keyboard_steps,
            "lighthouse_runs": lighthouse_runs,
            "max_parallel": max_parallel,
            "retain_body_sample": retain_body_sample,
        },
        "category_thresholds": thresholds,
        "boundaries": dict(REQUIRED_BOUNDARIES),
        "notes": notes,
    }


def load_validated_config(path: Path) -> tuple[dict[str, Any], str]:
    config = validate_config(load_json(path))
    return config, sha256_text(canonical_json(config))


def build_matrix(config: dict[str, Any]) -> dict[str, Any]:
    include = []
    target_by_id = {target["id"]: target for target in config["targets"]}
    for target_id in target_by_id:
        target = target_by_id[target_id]
        for profile in config["profiles"]:
            include.append(
                {
                    "target_id": target["id"],
                    "target_url": target["url"],
                    "target_kind": target["kind"],
                    "profile": profile,
                    "cell_id": f"{target['id']}-{profile}",
                }
            )
    return {"include": include}


def percentile_median(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if isinstance(value, (int, float))]
    if not present:
        return None
    return round(float(statistics.median(present)), 3)


def find_lighthouse_reports(input_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    reports: list[tuple[Path, dict[str, Any]]] = []
    for candidate in sorted(input_dir.rglob("*.json")):
        try:
            value = load_json(candidate)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value.get("categories"), dict) and isinstance(value.get("audits"), dict):
            reports.append((candidate, value))
    if not reports:
        raise ValueError(f"No Lighthouse reports found in {input_dir}")
    return reports


def category_score(report: dict[str, Any], category: str) -> int:
    raw = report.get("categories", {}).get(category, {})
    score = raw.get("score") if isinstance(raw, dict) else None
    if not isinstance(score, (int, float)):
        return 0
    return round(max(0.0, min(1.0, float(score))) * 100)


def audit_numeric(report: dict[str, Any], audit_id: str) -> float | None:
    raw = report.get("audits", {}).get(audit_id, {})
    value = raw.get("numericValue") if isinstance(raw, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def summarize_findings(reports: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ignored = {"notApplicable", "manual", "informative"}
    for report in reports:
        audits = report.get("audits", {})
        if not isinstance(audits, dict):
            continue
        for audit_id, raw in audits.items():
            if not isinstance(raw, dict) or raw.get("scoreDisplayMode") in ignored:
                continue
            score = raw.get("score")
            if not isinstance(score, (int, float)) or score >= 1:
                continue
            details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
            grouped[audit_id].append(
                {
                    "score": float(score),
                    "title": raw.get("title") or audit_id,
                    "display_value": raw.get("displayValue"),
                    "savings_ms": details.get("overallSavingsMs")
                    if isinstance(details.get("overallSavingsMs"), (int, float))
                    else None,
                }
            )
    findings = []
    for audit_id, values in grouped.items():
        findings.append(
            {
                "audit_id": audit_id,
                "title": values[0]["title"],
                "failed_run_count": len(values),
                "median_score": round(statistics.median(item["score"] for item in values), 3),
                "max_savings_ms": round(
                    max((item["savings_ms"] or 0) for item in values), 1
                ),
                "display_value": next(
                    (item["display_value"] for item in values if item["display_value"]), None
                ),
            }
        )
    findings.sort(
        key=lambda item: (
            -item["failed_run_count"],
            item["median_score"],
            -item["max_savings_ms"],
            item["audit_id"],
        )
    )
    return findings[:limit]


def summarize_lighthouse(
    config: dict[str, Any],
    config_hash: str,
    target_id: str,
    profile: str,
    input_dir: Path,
) -> dict[str, Any]:
    targets = {target["id"]: target for target in config["targets"]}
    if target_id not in targets:
        raise ValueError(f"Unknown target id: {target_id}")
    if profile not in config["profiles"]:
        raise ValueError(f"Profile is outside config: {profile}")
    report_pairs = find_lighthouse_reports(input_dir)
    reports = [report for _, report in report_pairs]
    expected_runs = config["settings"]["lighthouse_runs"]
    if len(reports) != expected_runs:
        raise ValueError(f"Expected {expected_runs} Lighthouse reports, found {len(reports)}")

    thresholds = config["category_thresholds"]
    categories: dict[str, Any] = {}
    failed_categories: list[str] = []
    for category in CATEGORIES:
        scores = [category_score(report, category) for report in reports]
        median_score = round(statistics.median(scores))
        threshold = round(thresholds[category] * 100)
        status = "PASS" if median_score >= threshold else "WARN"
        if status == "WARN":
            failed_categories.append(category)
        categories[category] = {
            "scores": scores,
            "median_score": median_score,
            "threshold": threshold,
            "status": status,
        }

    metrics = {
        "first_contentful_paint_ms": percentile_median(
            audit_numeric(report, "first-contentful-paint") for report in reports
        ),
        "largest_contentful_paint_ms": percentile_median(
            audit_numeric(report, "largest-contentful-paint") for report in reports
        ),
        "total_blocking_time_ms": percentile_median(
            audit_numeric(report, "total-blocking-time") for report in reports
        ),
        "cumulative_layout_shift": percentile_median(
            audit_numeric(report, "cumulative-layout-shift") for report in reports
        ),
        "speed_index_ms": percentile_median(
            audit_numeric(report, "speed-index") for report in reports
        ),
    }
    largest_gap = max(
        (value["threshold"] - value["median_score"] for value in categories.values()),
        default=0,
    )
    severity = "HIGH" if largest_gap >= 30 else "MEDIUM" if largest_gap >= 15 else "LOW"
    target = targets[target_id]
    raw_reports = [
        {
            "file": str(path.relative_to(input_dir)),
            "sha256": sha256_file(path),
            "requested_url": report.get("requestedUrl"),
            "final_url": report.get("finalUrl"),
            "fetch_time": report.get("fetchTime"),
            "lighthouse_version": report.get("lighthouseVersion"),
        }
        for path, report in report_pairs
    ]
    return {
        "schema_version": LIGHTHOUSE_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "company": config["company"],
        "target": target,
        "profile": profile,
        "config_sha256": config_hash,
        "run_count": len(reports),
        "verdict": "PASS" if not failed_categories else "WARN",
        "severity": severity,
        "categories": categories,
        "core_metrics": metrics,
        "top_findings": summarize_findings(reports),
        "raw_reports": raw_reports,
        "boundaries": {
            "public_web_quality_only": True,
            "security_vulnerability_claim": False,
            "compliance_certification": False,
        },
    }


def render_lighthouse_markdown(summary: dict[str, Any]) -> str:
    target = summary["target"]
    lines = [
        f"# LiminalQA · {summary['company']['name']} · {target['id']} · {summary['profile']}",
        "",
        f"**Verdict:** {summary['verdict']}  ",
        f"**Severity:** {summary['severity']}  ",
        f"**Target:** `{target['url']}`  ",
        f"**Lighthouse runs:** {summary['run_count']}",
        "",
        "## Category scores",
        "",
        "| Category | Scores | Median | Threshold | Status |",
        "|---|---|---:|---:|---|",
    ]
    for category, value in summary["categories"].items():
        scores = ", ".join(str(score) for score in value["scores"])
        lines.append(
            f"| {category} | {scores} | {value['median_score']} | {value['threshold']} | {value['status']} |"
        )
    lines.extend(["", "## Core metrics", ""])
    for key, value in summary["core_metrics"].items():
        lines.append(f"- **{key}:** {value if value is not None else 'n/a'}")
    lines.extend(["", "## Recurring findings", ""])
    for finding in summary["top_findings"][:8]:
        lines.append(
            f"- **{finding['title']}** — failed {finding['failed_run_count']}/{summary['run_count']} runs; median score {finding['median_score']}"
        )
    if not summary["top_findings"]:
        lines.append("No scored Lighthouse findings were returned.")
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "> Passive public web quality evidence only. This is not a penetration test,",
            "> security vulnerability report, or compliance certification.",
            "",
        ]
    )
    return "\n".join(lines)


def severity_rank(value: str) -> int:
    return {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(value, 0)


def classify_cell(browser: dict[str, Any], lighthouse: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    severity = "NONE"
    navigation = browser.get("navigation", {})
    status = navigation.get("status")
    if navigation.get("error") or not isinstance(status, int) or status >= 400:
        reasons.append("navigation_failed_or_non_success")
        severity = "HIGH"

    signals = browser.get("signals", {})
    accessibility_signals = {
        "keyboard_focus_gap": signals.get("keyboard_focus_gap", False),
        "unnamed_sequential_controls": int(signals.get("unnamed_sequential_controls", 0) or 0),
        "nested_interactive_controls": int(signals.get("nested_interactive_controls", 0) or 0),
        "unnamed_accessibility_controls": int(signals.get("unnamed_accessibility_controls", 0) or 0),
    }
    if accessibility_signals["keyboard_focus_gap"]:
        reasons.append("keyboard_focus_gap")
        if severity_rank(severity) < severity_rank("MEDIUM"):
            severity = "MEDIUM"
    for key in (
        "unnamed_sequential_controls",
        "nested_interactive_controls",
        "unnamed_accessibility_controls",
    ):
        if accessibility_signals[key] > 0:
            reasons.append(key)
            if severity_rank(severity) < severity_rank("MEDIUM"):
                severity = "MEDIUM"

    if lighthouse.get("verdict") == "WARN":
        reasons.append("lighthouse_threshold_warning")
        lighthouse_severity = lighthouse.get("severity", "LOW")
        if severity_rank(lighthouse_severity) > severity_rank(severity):
            severity = lighthouse_severity

    if int(browser.get("console", {}).get("error_count", 0) or 0) > 0:
        reasons.append("console_errors_observed")
        if severity_rank(severity) < severity_rank("LOW"):
            severity = "LOW"

    return {
        "verdict": "PASS" if not reasons else "WARN",
        "severity": severity,
        "reasons": reasons,
        "accessibility_signals": accessibility_signals,
    }


def parse_sha256_manifest(path: Path) -> list[dict[str, str]]:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ValueError(f"Invalid SHA256 manifest line in {path}: {line}")
        entries.append({"sha256": parts[0], "file": parts[1].lstrip("* ")})
    return entries


def aggregate_results(
    config: dict[str, Any],
    config_hash: str,
    input_dir: Path,
    run_id: str,
    run_attempt: str,
    caller_repository: str,
    caller_sha: str,
    engine_sha: str,
) -> dict[str, Any]:
    expected_cells = {
        f"{target['id']}-{profile}"
        for target in config["targets"]
        for profile in config["profiles"]
    }
    manifests = sorted(input_dir.rglob("exact-attempt.json"))
    if len(manifests) != len(expected_cells):
        raise ValueError(
            f"Expected {len(expected_cells)} exact-attempt manifests, found {len(manifests)}"
        )

    cells: list[dict[str, Any]] = []
    seen: set[str] = set()
    for manifest_path in manifests:
        artifact_dir = manifest_path.parent
        manifest = load_json(manifest_path)
        required = {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "caller_repository": caller_repository,
            "caller_sha": caller_sha,
            "engine_sha": engine_sha,
            "config_sha256": config_hash,
        }
        for key, expected in required.items():
            if str(manifest.get(key)) != str(expected):
                raise ValueError(
                    f"Manifest mismatch for {key} in {manifest_path}: {manifest.get(key)!r} != {expected!r}"
                )
        cell_id = require_string(manifest.get("cell_id"), "manifest.cell_id", 1, 100)
        if cell_id not in expected_cells:
            raise ValueError(f"Unexpected cell id: {cell_id}")
        if cell_id in seen:
            raise ValueError(f"Duplicate cell id: {cell_id}")
        seen.add(cell_id)

        browser_path = artifact_dir / "browser-result.json"
        lighthouse_path = artifact_dir / "lighthouse-summary.json"
        sums_path = artifact_dir / "SHA256SUMS.txt"
        for required_path in (browser_path, lighthouse_path, sums_path):
            if not required_path.is_file():
                raise ValueError(f"Missing evidence file: {required_path}")
        browser = load_json(browser_path)
        lighthouse = load_json(lighthouse_path)
        classification = classify_cell(browser, lighthouse)
        target_id = manifest["target_id"]
        profile = manifest["profile"]
        cells.append(
            {
                "cell_id": cell_id,
                "target_id": target_id,
                "profile": profile,
                "target_url": manifest["target_url"],
                "classification": classification,
                "navigation": browser.get("navigation"),
                "browser_signals": browser.get("signals"),
                "lighthouse": {
                    "verdict": lighthouse.get("verdict"),
                    "severity": lighthouse.get("severity"),
                    "categories": lighthouse.get("categories"),
                    "core_metrics": lighthouse.get("core_metrics"),
                    "top_findings": lighthouse.get("top_findings", [])[:8],
                },
                "evidence": {
                    "artifact_directory": artifact_dir.name,
                    "manifest_sha256": sha256_file(manifest_path),
                    "browser_result_sha256": sha256_file(browser_path),
                    "lighthouse_summary_sha256": sha256_file(lighthouse_path),
                    "sha256_manifest_sha256": sha256_file(sums_path),
                    "files": parse_sha256_manifest(sums_path),
                },
            }
        )

    missing = expected_cells - seen
    if missing:
        raise ValueError(f"Missing cells: {', '.join(sorted(missing))}")
    cells.sort(key=lambda cell: (cell["target_id"], cell["profile"]))

    warning_cells = [cell for cell in cells if cell["classification"]["verdict"] == "WARN"]
    severity = max(
        (cell["classification"]["severity"] for cell in cells),
        key=severity_rank,
        default="NONE",
    )
    reason_counts = Counter(
        reason for cell in cells for reason in cell["classification"]["reasons"]
    )
    recurring_lighthouse = Counter(
        finding["audit_id"]
        for cell in cells
        for finding in cell["lighthouse"]["top_findings"]
    )

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "company": config["company"],
        "verdict": "PASS" if not warning_cells else "WARN",
        "severity": severity,
        "summary": {
            "target_count": len(config["targets"]),
            "profile_count": len(config["profiles"]),
            "cell_count": len(cells),
            "pass_cells": len(cells) - len(warning_cells),
            "warning_cells": len(warning_cells),
            "reason_counts": dict(sorted(reason_counts.items())),
            "recurring_lighthouse_findings": [
                {"audit_id": audit_id, "cell_count": count}
                for audit_id, count in recurring_lighthouse.most_common(15)
            ],
        },
        "provenance": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "caller_repository": caller_repository,
            "caller_sha": caller_sha,
            "engine_repository": "safal207/LiminalQAengineer",
            "engine_sha": engine_sha,
            "config_sha256": config_hash,
        },
        "coordinate_model": {
            "O": "allowlisted public URL + browser profile + viewport + unauthenticated state + observation time",
            "N": "passive browser, keyboard observer, and Lighthouse quality sensor",
            "X": "company -> route -> component -> quality/accessibility signal",
            "Y": "loading -> rendered -> accessible -> focusable or degraded",
            "Z": "desktop/mobile profile",
            "T": "navigation -> settle -> keyboard trace -> Lighthouse capture -> aggregation",
        },
        "cells": cells,
        "boundaries": config["boundaries"],
        "limitations": [
            "The pipeline observes only the allowlisted public URLs in the supplied contract.",
            "Lighthouse scores and automated DOM signals are triage evidence, not final proof of a product defect.",
            "The result is not a penetration test, security vulnerability report, or compliance certification.",
            "No credentials, accounts, forms, direct application APIs, state changes, fuzzing, or load testing are supported.",
        ],
        "authority": {
            "mode": "evidence_only",
            "grants": {
                "ownership": False,
                "approval": False,
                "external_submission": False,
                "deployment": False,
                "merge": False,
            },
        },
    }


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_portfolio_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# LiminalQA self-service audit · {result['company']['name']}",
        "",
        f"**Audit:** {result['company']['audit_name']}  ",
        f"**Verdict:** {result['verdict']}  ",
        f"**Highest quality severity:** {result['severity']}  ",
        f"**Run:** `{result['provenance']['run_id']}` attempt `{result['provenance']['run_attempt']}`",
        "",
        "## Portfolio",
        "",
        "| Target | Profile | HTTP | Lighthouse | Perf | A11y | Best | SEO | Browser reasons |",
        "|---|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for cell in result["cells"]:
        categories = cell["lighthouse"]["categories"] or {}
        score = lambda name: categories.get(name, {}).get("median_score", "n/a")
        status = (cell.get("navigation") or {}).get("status", "n/a")
        reasons = ", ".join(cell["classification"]["reasons"]) or "—"
        lines.append(
            "| {target} | {profile} | {http} | {lh} | {perf} | {a11y} | {best} | {seo} | {reasons} |".format(
                target=markdown_escape(cell["target_id"]),
                profile=markdown_escape(cell["profile"]),
                http=status,
                lh=cell["lighthouse"]["verdict"],
                perf=score("performance"),
                a11y=score("accessibility"),
                best=score("best-practices"),
                seo=score("seo"),
                reasons=markdown_escape(reasons),
            )
        )
    lines.extend(["", "## Recurring signals", ""])
    if result["summary"]["reason_counts"]:
        for reason, count in result["summary"]["reason_counts"].items():
            lines.append(f"- **{reason}:** {count} cells")
    else:
        lines.append("No automated warning signals were produced.")
    lines.extend(["", "## Evidence provenance", ""])
    for key, value in result["provenance"].items():
        lines.append(f"- **{key}:** `{value}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "> Public, allowlisted, passive quality and accessibility evidence only.",
            "> Not a penetration test, vulnerability report, or compliance certification.",
            "",
        ]
    )
    return "\n".join(lines)


def render_evidence_index(result: dict[str, Any]) -> str:
    lines = [
        f"# Evidence index · {result['company']['name']}",
        "",
        "| Cell | Browser result SHA-256 | Lighthouse summary SHA-256 | Manifest SHA-256 |",
        "|---|---|---|---|",
    ]
    for cell in result["cells"]:
        evidence = cell["evidence"]
        lines.append(
            f"| {cell['cell_id']} | `{evidence['browser_result_sha256']}` | `{evidence['lighthouse_summary_sha256']}` | `{evidence['manifest_sha256']}` |"
        )
    lines.extend(
        [
            "",
            "A workflow success state is not treated as proof by itself. The evidence consists of",
            "the exact manifests, result content, screenshots, raw Lighthouse reports, and hashes.",
            "",
        ]
    )
    return "\n".join(lines)


def command_validate(args: argparse.Namespace) -> int:
    config, config_hash = load_validated_config(Path(args.config))
    if args.output:
        write_json(Path(args.output), config)
    print(json.dumps({"config_sha256": config_hash, "company": config["company"]}))
    return 0


def command_matrix(args: argparse.Namespace) -> int:
    config, config_hash = load_validated_config(Path(args.config))
    value = build_matrix(config)
    value["config_sha256"] = config_hash
    value["max_parallel"] = config["settings"]["max_parallel"]
    print(json.dumps(value, separators=(",", ":")))
    return 0


def command_summarize_lighthouse(args: argparse.Namespace) -> int:
    config, config_hash = load_validated_config(Path(args.config))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_lighthouse(
        config,
        config_hash,
        args.target_id,
        args.profile,
        Path(args.input_dir),
    )
    write_json(output_dir / "lighthouse-summary.json", summary)
    (output_dir / "lighthouse-summary.md").write_text(
        render_lighthouse_markdown(summary), encoding="utf-8"
    )
    return 0


def command_aggregate(args: argparse.Namespace) -> int:
    config, config_hash = load_validated_config(Path(args.config))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = aggregate_results(
        config,
        config_hash,
        Path(args.input_dir),
        str(args.run_id),
        str(args.run_attempt),
        args.caller_repository,
        args.caller_sha,
        args.engine_sha,
    )
    result_path = output_dir / "company-audit-result.json"
    summary_path = output_dir / "company-audit-summary.md"
    index_path = output_dir / "evidence-index.md"
    write_json(result_path, result)
    summary_path.write_text(render_portfolio_markdown(result), encoding="utf-8")
    index_path.write_text(render_evidence_index(result), encoding="utf-8")
    outputs = {
        "verdict": result["verdict"],
        "severity": result["severity"],
        "result_sha256": sha256_file(result_path),
        "summary_sha256": sha256_file(summary_path),
        "evidence_index_sha256": sha256_file(index_path),
    }
    write_json(output_dir / "workflow-outputs.json", outputs)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--config", required=True)
    validate.add_argument("--output")
    validate.set_defaults(func=command_validate)

    matrix = subparsers.add_parser("matrix")
    matrix.add_argument("--config", required=True)
    matrix.set_defaults(func=command_matrix)

    lighthouse = subparsers.add_parser("summarize-lighthouse")
    lighthouse.add_argument("--config", required=True)
    lighthouse.add_argument("--target-id", required=True)
    lighthouse.add_argument("--profile", required=True)
    lighthouse.add_argument("--input-dir", required=True)
    lighthouse.add_argument("--output-dir", required=True)
    lighthouse.set_defaults(func=command_summarize_lighthouse)

    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--config", required=True)
    aggregate.add_argument("--input-dir", required=True)
    aggregate.add_argument("--output-dir", required=True)
    aggregate.add_argument("--run-id", required=True)
    aggregate.add_argument("--run-attempt", required=True)
    aggregate.add_argument("--caller-repository", required=True)
    aggregate.add_argument("--caller-sha", required=True)
    aggregate.add_argument("--engine-sha", required=True)
    aggregate.set_defaults(func=command_aggregate)
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
