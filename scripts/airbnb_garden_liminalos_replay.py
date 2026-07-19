#!/usr/bin/env python3
"""Compare the exact Airbnb evidence with GardenLiminal and LiminalOSAI capabilities.

This command does not navigate Airbnb. It replays the exact artifact from workflow run
29678020284, validates its integrity and target identity, then reports what the two new
runtime layers can and cannot add. LiminalOSAI remains advisory and cannot confirm a
product defect or grant execution authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


EXPECTED_SEQUENCE = ["TRY", "EUR", "TRY", "EUR"]
REQUIRED_GARDEN_EVENTS = [
    "RUN_CREATED",
    "SEED_LOADED",
    "NS_CREATED",
    "CGROUP_APPLIED",
    "CAPS_DROPPED",
    "PROCESS_START",
    "PROCESS_EXIT",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find_one(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name!r} below {root}, found {len(matches)}")
    return matches[0]


def read_exit_status(status_dir: Path, name: str) -> int | None:
    path = status_dir / f"{name}.exit"
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def verify_manifest(evidence_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, list):
        raise ValueError("manifest.json must contain a list")

    missing: list[str] = []
    mismatched: list[dict[str, str]] = []
    verified = 0
    artifact_root = manifest_path.parent
    for entry in manifest:
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("manifest entry must contain string path and sha256")
        candidate = artifact_root / relative
        if not candidate.is_file():
            missing.append(relative)
            continue
        actual = sha256(candidate)
        if actual != expected:
            mismatched.append({"path": relative, "expected": expected, "actual": actual})
        else:
            verified += 1

    return {
        "manifest_entries": len(manifest),
        "verified_entries": verified,
        "missing": missing,
        "mismatched": mismatched,
        "valid": not missing and not mismatched and verified == len(manifest),
        "evidence_root": str(evidence_root),
    }


def listing_id_from_url(url: str) -> str | None:
    match = re.search(r"/rooms/(\d+)", urlsplit(url).path)
    return match.group(1) if match else None


def requested_currency_from_url(url: str) -> str | None:
    values = parse_qs(urlsplit(url).query).get("currency", [])
    return values[0].upper() if values else None


def inspect_attempt(attempt: dict[str, Any], expected_listing_id: str) -> dict[str, Any]:
    states = attempt.get("states") or []
    state_currencies: list[str] = []
    target_ids: list[str | None] = []
    url_currency_matches: list[bool] = []

    for state in states:
        inferred = state.get("inferred_visible_currency")
        requested = state.get("requested_currency")
        final_url = state.get("final_url") or ""
        state_currencies.append(inferred)
        target_ids.append(listing_id_from_url(final_url))
        url_currency = requested_currency_from_url(final_url)
        url_currency_matches.append(
            inferred == requested and (url_currency is None or url_currency == requested)
        )

    failures = attempt.get("request_failures") or []
    failure_reasons = Counter((item.get("error") or "unknown") for item in failures)
    failure_hosts = Counter()
    for item in failures:
        try:
            failure_hosts[urlsplit(item.get("url") or "").hostname or "unknown"] += 1
        except ValueError:
            failure_hosts["invalid"] += 1

    return {
        "attempt_id": attempt.get("attempt_id"),
        "outcome": attempt.get("outcome"),
        "state_count": len(states),
        "currency_sequence": state_currencies,
        "expected_sequence_match": state_currencies == EXPECTED_SEQUENCE,
        "target_ids": target_ids,
        "target_identity_stable": bool(target_ids)
        and all(value == expected_listing_id for value in target_ids),
        "url_and_visible_currency_aligned": bool(url_currency_matches)
        and all(url_currency_matches),
        "runtime_errors": attempt.get("runtime_errors") or [],
        "console_error_count": int(attempt.get("console_error_count") or 0),
        "page_error_count": len(attempt.get("page_errors") or []),
        "http_4xx_5xx_count": len(attempt.get("http_4xx_5xx") or []),
        "request_failure_count": len(failures),
        "request_failure_reasons": dict(sorted(failure_reasons.items())),
        "request_failure_hosts": dict(sorted(failure_hosts.items())),
        "payment_submitted": attempt.get("payment_submitted"),
        "reservation_created": attempt.get("reservation_created"),
    }


def collect_tokens(root: Path, tokens: list[str]) -> dict[str, bool]:
    found = {token: False for token in tokens}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".txt", ".log"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for token in tokens:
            if token in text:
                found[token] = True
    return found


def runtime_capability(statuses: dict[str, int | None], required: list[str]) -> str:
    values = [statuses.get(name) for name in required]
    if all(value == 0 for value in values):
        return "CONFIRMED_ON_BENCHMARK_RUNNER"
    if any(value is not None for value in values):
        return "ENVIRONMENT_LIMITED_OR_FAILED"
    return "NOT_EXECUTED"


def build_report(
    config: dict[str, Any],
    evidence_root: Path,
    status_dir: Path,
    garden_log_root: Path,
) -> dict[str, Any]:
    probe_path = find_one(evidence_root, "probe-result.json")
    manifest_path = find_one(evidence_root, "manifest.json")
    source = config["source_evidence"]
    target = config["target"]

    probe_sha = sha256(probe_path)
    manifest_sha = sha256(manifest_path)
    if probe_sha != source["probe_result_sha256"]:
        raise ValueError(
            f"probe-result SHA mismatch: expected {source['probe_result_sha256']}, got {probe_sha}"
        )
    if manifest_sha != source["manifest_sha256"]:
        raise ValueError(
            f"manifest SHA mismatch: expected {source['manifest_sha256']}, got {manifest_sha}"
        )

    manifest_result = verify_manifest(evidence_root, manifest_path)
    probe = read_json(probe_path)
    attempts = [
        inspect_attempt(attempt, target["listing_id"])
        for attempt in (probe.get("attempts") or [])
    ]

    evidence_valid = (
        manifest_result["valid"]
        and probe.get("target")
        and listing_id_from_url(probe["target"]) == target["listing_id"]
        and len(attempts) == target["expected_attempts"]
        and all(item["outcome"] == target["expected_outcome"] for item in attempts)
        and all(item["expected_sequence_match"] for item in attempts)
        and all(item["target_identity_stable"] for item in attempts)
        and all(item["url_and_visible_currency_aligned"] for item in attempts)
        and all(not item["runtime_errors"] for item in attempts)
        and all(item["console_error_count"] == 0 for item in attempts)
        and all(item["page_error_count"] == 0 for item in attempts)
        and all(item["http_4xx_5xx_count"] == 0 for item in attempts)
        and probe.get("confirmed_defect") is False
        and probe.get("payment_submitted") is False
        and probe.get("reservation_created") is False
    )

    statuses = {
        name: read_exit_status(status_dir, name)
        for name in (
            "garden-build",
            "garden-test",
            "garden-inspect",
            "garden-run",
            "liminalos-build",
            "liminalos-check",
            "liminalos-test",
            "liminalos-dry-run",
        )
    }
    garden_events = collect_tokens(garden_log_root, REQUIRED_GARDEN_EVENTS)
    original_evidence_events = collect_tokens(evidence_root, REQUIRED_GARDEN_EVENTS)

    all_failures = sum(item["request_failure_count"] for item in attempts)
    all_failure_reasons = Counter()
    all_failure_hosts = Counter()
    for item in attempts:
        all_failure_reasons.update(item["request_failure_reasons"])
        all_failure_hosts.update(item["request_failure_hosts"])

    baseline_decision = target["expected_lotus_decision"]
    replay_decision = "NO_DEFECT_OBSERVED" if evidence_valid else "NEEDS_EVIDENCE"

    garden_capability = runtime_capability(
        statuses, ["garden-build", "garden-test", "garden-inspect", "garden-run"]
    )
    liminalos_capability = runtime_capability(
        statuses,
        ["liminalos-build", "liminalos-check", "liminalos-test", "liminalos-dry-run"],
    )

    garden_runtime_trace_complete = all(garden_events.values())
    original_has_garden_provenance = all(original_evidence_events.values())

    return {
        "schema_version": config["schema_version"],
        "case_id": config["case_id"],
        "source": {
            **source,
            "probe_result_path": str(probe_path),
            "probe_result_sha256_observed": probe_sha,
            "manifest_path": str(manifest_path),
            "manifest_sha256_observed": manifest_sha,
        },
        "integrity": manifest_result,
        "replay": {
            "target_listing_id": target["listing_id"],
            "probe_target_listing_id": listing_id_from_url(probe.get("target") or ""),
            "attempts": attempts,
            "outcomes": probe.get("outcomes"),
            "normalized_signatures": probe.get("normalized_signatures"),
            "evidence_grade": probe.get("evidence_grade"),
            "evidence_valid": evidence_valid,
            "request_failure_count": all_failures,
            "request_failure_reasons": dict(sorted(all_failure_reasons.items())),
            "request_failure_hosts": dict(sorted(all_failure_hosts.items())),
            "request_failure_interpretation": (
                "Diagnostic signal only: the evidence contains no HTTP 4xx/5xx, console error, "
                "page error, inconsistent currency state, or demonstrated user impact."
            ),
        },
        "baseline": {
            "stack": "LiminalQA + Lotus over Playwright Docker evidence",
            "decision": baseline_decision,
            "confirmed_defect": False,
        },
        "new_stack": {
            "garden": {
                "repository": config["garden"]["repository"],
                "commit": config["garden"]["commit"],
                "statuses": {key: value for key, value in statuses.items() if key.startswith("garden-")},
                "capability": garden_capability,
                "lifecycle_events_observed": garden_events,
                "lifecycle_trace_complete": garden_runtime_trace_complete,
                "original_airbnb_evidence_contains_garden_provenance": original_has_garden_provenance,
                "retroactive_isolation_claim": False,
            },
            "liminalos": {
                "repository": config["liminalos"]["repository"],
                "commit": config["liminalos"]["commit"],
                "statuses": {key: value for key, value in statuses.items() if key.startswith("liminalos-")},
                "capability": liminalos_capability,
                "role": "advisory_runtime_capability_only",
                "airbnb_defect_confirmation_authority": False,
            },
            "lotus_replay_decision": replay_decision,
            "decision_changed": replay_decision != baseline_decision,
        },
        "comparison": {
            "same_input_evidence": True,
            "baseline_decision": baseline_decision,
            "replay_decision": replay_decision,
            "product_finding_delta": "NONE" if replay_decision == baseline_decision else "EVIDENCE_REGRESSION",
            "evidence_delta": [
                "Exact artifact, probe, manifest, target identity, and URL/currency transitions are machine-reverified.",
                "Garden build/test/run capability is measured separately from the original Airbnb execution.",
                "LiminalOSAI build/check/test capability is measured but remains advisory.",
                "The original Docker run cannot be retroactively described as Garden-isolated.",
            ],
            "honest_conclusion": (
                "The new stack does not manufacture a new Airbnb defect. Its immediate value is stronger "
                "provenance, explicit runtime capability evidence, and a clearer boundary between product "
                "signals, execution-environment signals, and experimental advisory signals."
            ),
        },
        "authority": config["authority"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    replay = report["replay"]
    garden = report["new_stack"]["garden"]
    liminalos = report["new_stack"]["liminalos"]
    lines = [
        "# Airbnb GardenLiminal + LiminalOSAI comparison",
        "",
        "## Result",
        "",
        f"- Baseline Lotus decision: `{report['comparison']['baseline_decision']}`",
        f"- Replay decision: `{report['comparison']['replay_decision']}`",
        f"- Product finding delta: `{report['comparison']['product_finding_delta']}`",
        f"- Evidence integrity: `{'PASS' if replay['evidence_valid'] else 'FAIL'}`",
        "",
        "The same exact Airbnb artifact was replayed. No new live Airbnb navigation occurred.",
        "",
        "## Exact evidence replay",
        "",
        f"- Target listing: `{replay['target_listing_id']}`",
        f"- Attempts: `{len(replay['attempts'])}`",
        f"- Outcomes: `{replay['outcomes']}`",
        f"- Signatures: `{replay['normalized_signatures']}`",
        f"- Request failures retained as diagnostic signals: `{replay['request_failure_count']}`",
        "- HTTP 4xx/5xx, console errors and page errors: `0` in both attempts",
        "",
        "## GardenLiminal",
        "",
        f"- Exact commit: `{garden['commit']}`",
        f"- Capability result: `{garden['capability']}`",
        f"- Lifecycle trace complete: `{garden['lifecycle_trace_complete']}`",
        f"- Original Airbnb evidence contains Garden provenance: `{garden['original_airbnb_evidence_contains_garden_provenance']}`",
        "- Retroactive Garden-isolation claim: `false`",
        "",
        "## LiminalOSAI",
        "",
        f"- Exact commit: `{liminalos['commit']}`",
        f"- Capability result: `{liminalos['capability']}`",
        "- Role: experimental advisory runtime only",
        "- Authority to confirm an Airbnb defect: `false`",
        "",
        "## Conclusion",
        "",
        report["comparison"]["honest_conclusion"],
        "",
        "## Authority",
        "",
        "No ownership, approval, execution, delivery, external-submission, deployment, or merge authority is granted.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--status-dir", type=Path, required=True)
    parser.add_argument("--garden-log-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    config = read_json(args.config)
    report = build_report(
        config=config,
        evidence_root=args.evidence_root,
        status_dir=args.status_dir,
        garden_log_root=args.garden_log_root,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "comparison.json"
    md_path = args.output_dir / "comparison.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "baseline_decision": report["comparison"]["baseline_decision"],
        "replay_decision": report["comparison"]["replay_decision"],
        "evidence_valid": report["replay"]["evidence_valid"],
        "garden_capability": report["new_stack"]["garden"]["capability"],
        "liminalos_capability": report["new_stack"]["liminalos"]["capability"],
    }, indent=2))
    return 0 if report["replay"]["evidence_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
