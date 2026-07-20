#!/usr/bin/env python3
"""Build public issue evidence and a reference collapsed-tool visibility matrix.

This script does not claim access to Claude Code's private TUI implementation. It
fetches public issue metadata/comments, constructs a disclosed reference renderer,
and tests a bounded product contract derived from the issue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

API_ROOT = "https://api.github.com"
USER_AGENT = "LiminalQAengineer-boris-primary-identifier-evidence/1.0"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def request_json(url: str, token: str | None) -> tuple[Any, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} for {url}: {body[:500]}") from exc


def fetch_issue_and_comments(repository: str, issue_number: int, token: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issue, _ = request_json(f"{API_ROOT}/repos/{repository}/issues/{issue_number}", token)
    comments: list[dict[str, Any]] = []
    page = 1
    while True:
        batch, _ = request_json(
            f"{API_ROOT}/repos/{repository}/issues/{issue_number}/comments?per_page=100&page={page}",
            token,
        )
        if not isinstance(batch, list):
            raise RuntimeError("GitHub comments response is not a list")
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 10:
            raise RuntimeError("Unexpectedly large issue comment pagination")
    return issue, comments


def signal_names(text: str) -> list[str]:
    lowered = text.lower()
    signals: list[str] = []
    if "2.1.20" in lowered and "2.1.19" in lowered:
        signals.append("regression_2_1_19_to_2_1_20")
    if "search pattern" in lowered or "search patterns" in lowered:
        signals.append("search_pattern_hidden")
    if "ctrl+o" in lowered and any(word in lowered for word in ("friction", "solution", "expand")):
        signals.append("ctrl_o_not_sufficient")
    if "config option" in lowered or "configuration option" in lowered or "provide a config" in lowered:
        signals.append("configuration_requested")
    if "blocked" in lowered and any(word in lowered for word in ("path", "file", "read")):
        signals.append("blocked_identifier_needed")
    if "audit trail" in lowered or "audit" in lowered:
        signals.append("auditability_needed")
    if "wrong files" in lowered or "wrong file" in lowered or "wrong directory" in lowered:
        signals.append("steering_failure_risk")
    if "monorepo" in lowered:
        signals.append("monorepo_context")
    if "vibe coding" in lowered or "power user" in lowered or "serious developer" in lowered:
        signals.append("expert_observability_preference")
    return sorted(set(signals))


def summarize_public_evidence(issue: dict[str, Any], comments: list[dict[str, Any]]) -> dict[str, Any]:
    issue_body = issue.get("body") or ""
    issue_signals = signal_names(issue_body)
    signal_comments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    authors: set[str] = set()
    comment_hashes: list[str] = []
    for comment in comments:
        body = comment.get("body") or ""
        login = (comment.get("user") or {}).get("login") or "unknown"
        authors.add(login)
        digest = sha256_text(body)
        comment_hashes.append(digest)
        for signal in signal_names(body):
            signal_comments[signal].append(
                {
                    "comment_id": comment.get("id"),
                    "url": comment.get("html_url"),
                    "author": login,
                    "body_sha256": digest,
                }
            )

    combined_signals = Counter(issue_signals)
    for signal, values in signal_comments.items():
        combined_signals[signal] += len(values)

    selected: dict[str, list[dict[str, Any]]] = {}
    for signal, values in sorted(signal_comments.items()):
        selected[signal] = values[:5]

    return {
        "issue_body_sha256": sha256_text(issue_body),
        "comment_body_chain_sha256": sha256_text("\n".join(comment_hashes)),
        "comment_count_fetched": len(comments),
        "unique_comment_authors": len(authors),
        "issue_body_signals": issue_signals,
        "signal_counts": dict(sorted(combined_signals.items())),
        "selected_signal_records": selected,
        "privacy_boundary": "Comment bodies are hashed; only signal labels, IDs, URLs, and authors are retained.",
    }


def plural(count: int, singular: str, plural_value: str | None = None) -> str:
    return singular if count == 1 else (plural_value or singular + "s")


def truncate_middle(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length < 9:
        return value[:max_length]
    left = (max_length - 1) // 2
    right = max_length - left - 1
    return value[:left] + "…" + value[-right:]


def identifier_recognizable(rendered: str, identifier: str, max_length: int) -> bool:
    """Require full identity when it fits; otherwise preserve stable prefix and suffix."""
    if identifier in rendered:
        return True
    if len(identifier) <= max_length:
        return False
    anchor_length = min(16, max(6, max_length // 8))
    return identifier[:anchor_length] in rendered and identifier[-anchor_length:] in rendered


def normalize_path(value: str, workspace: str) -> str:
    normalized = value.replace("\\", "/")
    workspace_norm = workspace.rstrip("/")
    if normalized == workspace_norm:
        return "."
    if normalized.startswith(workspace_norm + "/"):
        return normalized[len(workspace_norm) + 1 :]

    home_match = re.match(r"^/(?:Users|home)/[^/]+/(.+)$", normalized)
    if home_match:
        return "~/" + home_match.group(1)

    if normalized.startswith("/"):
        parts = PurePosixPath(normalized).parts
        visible = parts[-3:] if len(parts) >= 3 else parts
        return "…/" + "/".join(part for part in visible if part != "/")
    return normalized


def normalize_identifier(tool: str, value: str, workspace: str) -> str:
    if tool in {"Read", "Write", "Edit"}:
        return normalize_path(value, workspace)
    return value


def outcome_prefix(outcome: str) -> str:
    return {
        "success": "",
        "blocked": "Blocked ",
        "permission_denied": "Denied ",
        "error": "Failed ",
    }[outcome]


def reported_collapsed_model(tool: str, identifiers: list[str], outcome: str) -> str:
    """Model only the abstraction reported by the issue, not private product code."""
    count = len(identifiers)
    prefix = outcome_prefix(outcome)
    if tool == "Read":
        return f"{prefix}Read {count} {plural(count, 'file')}"
    if tool == "Write":
        return f"{prefix}Wrote {count} {plural(count, 'file')}"
    if tool == "Edit":
        return f"{prefix}Edited {count} {plural(count, 'file')}"
    return f"{prefix}Searched {count} {plural(count, 'pattern')}"


def reference_collapsed_renderer(
    tool: str,
    identifiers: list[str],
    outcome: str,
    *,
    workspace: str,
    max_length: int,
    multi_limit: int,
) -> tuple[str, list[str]]:
    normalized = [normalize_identifier(tool, value, workspace) for value in identifiers]
    prefix = outcome_prefix(outcome)
    noun = "files" if tool in {"Read", "Write", "Edit"} else "patterns"
    if len(normalized) == 1:
        rendered = f"{prefix}{tool}: {normalized[0]}"
    else:
        visible = normalized[:multi_limit]
        remainder = len(normalized) - len(visible)
        suffix = f" +{remainder}" if remainder else ""
        rendered = f"{prefix}{tool} {len(normalized)} {noun}: {', '.join(visible)}{suffix}"
    return truncate_middle(rendered, max_length), normalized


def identifier_sets() -> dict[str, dict[str, dict[str, list[str]]]]:
    return {
        "Read": {
            "single": {
                "a": ["/workspace/project/src/auth/session.ts"],
                "b": ["/workspace/project/packages/payments/session.ts"],
            },
            "multiple": {
                "a": [
                    "/workspace/project/src/auth/session.ts",
                    "/workspace/project/src/auth/token.ts",
                    "/workspace/project/src/auth/config.ts",
                ],
                "b": [
                    "/workspace/project/packages/web/session.ts",
                    "/workspace/project/packages/web/token.ts",
                    "/workspace/project/packages/web/config.ts",
                ],
            },
        },
        "Write": {
            "single": {
                "a": ["/workspace/project/docs/release-plan.md"],
                "b": ["/workspace/project/docs/migration-plan.md"],
            },
            "multiple": {
                "a": [
                    "/workspace/project/docs/release-plan.md",
                    "/workspace/project/docs/changelog.md",
                    "/workspace/project/docs/rollback.md",
                ],
                "b": [
                    "/workspace/project/reports/audit.md",
                    "/workspace/project/reports/findings.md",
                    "/workspace/project/reports/evidence.md",
                ],
            },
        },
        "Edit": {
            "single": {
                "a": ["/workspace/project/src/api/client.ts"],
                "b": ["/workspace/project/src/api/server.ts"],
            },
            "multiple": {
                "a": [
                    "/workspace/project/src/api/client.ts",
                    "/workspace/project/src/api/types.ts",
                    "/workspace/project/src/api/errors.ts",
                ],
                "b": [
                    "/workspace/project/src/db/client.ts",
                    "/workspace/project/src/db/types.ts",
                    "/workspace/project/src/db/errors.ts",
                ],
            },
        },
        "Glob": {
            "single": {"a": ["src/**/*.ts"], "b": ["tests/**/*.ts"]},
            "multiple": {
                "a": ["src/**/*.ts", "tests/**/*.ts", "packages/*/src/**/*.ts"],
                "b": ["docs/**/*.md", "examples/**/*.md", "fixtures/**/*.json"],
            },
        },
        "Grep": {
            "single": {"a": ["TODO|FIXME"], "b": ["deprecated|legacy"]},
            "multiple": {
                "a": ["TODO|FIXME", "unsafe", "temporary workaround"],
                "b": ["password", "secret", "private key"],
            },
        },
    }


def build_scenarios(config: dict[str, Any]) -> list[dict[str, Any]]:
    contract = config["contract"]
    workspace = contract["workspace"]
    max_length = int(contract["max_collapsed_length"])
    multi_limit = int(contract["multi_identifier_limit"])
    sets = identifier_sets()
    scenarios: list[dict[str, Any]] = []
    sequence = 0

    for tool in contract["required_tools"]:
        for cardinality in contract["required_cardinalities"]:
            for outcome in contract["required_outcomes"]:
                for variant, identifiers in sets[tool][cardinality].items():
                    sequence += 1
                    current = reported_collapsed_model(tool, identifiers, outcome)
                    proposed, normalized = reference_collapsed_renderer(
                        tool,
                        identifiers,
                        outcome,
                        workspace=workspace,
                        max_length=max_length,
                        multi_limit=multi_limit,
                    )
                    identifier_visible = all(
                        identifier_recognizable(proposed, identifier, max_length)
                        for identifier in normalized[:multi_limit]
                    )
                    outcome_visible = outcome == "success" or proposed.startswith(outcome_prefix(outcome))
                    workspace_private = not any(
                        re.search(r"/(?:Users|home)/[^/]+/", proposed) for _ in [0]
                    )
                    content_safe = all("\n" not in item for item in normalized)
                    compact = len(proposed) <= max_length
                    lpi_states = [
                        {"state": "Hello", "detail": {"tool": tool, "cardinality": cardinality}},
                        {"state": "Mirror", "detail": {"normalized_identifiers": normalized}},
                        {"state": "Bind", "detail": {"outcome": outcome, "surface": "collapsed"}},
                        {
                            "state": "Seal",
                            "detail": {
                                "identifier_visible": identifier_visible,
                                "outcome_visible": outcome_visible,
                                "compact": compact,
                                "workspace_private": workspace_private,
                            },
                        },
                        {"state": "Flow", "detail": {"rendered": proposed}},
                    ]
                    scenarios.append(
                        {
                            "scenario_id": f"core-{sequence:03d}",
                            "tool": tool,
                            "cardinality": cardinality,
                            "outcome": outcome,
                            "variant": variant,
                            "identifiers": identifiers,
                            "normalized_identifiers": normalized,
                            "reported_collapsed_model": current,
                            "reference_collapsed_output": proposed,
                            "checks": {
                                "identifier_visible": identifier_visible,
                                "outcome_visible": outcome_visible,
                                "workspace_private": workspace_private,
                                "content_safe": content_safe,
                                "compact": compact,
                                "critical_identifier_visible": (
                                    identifier_visible if outcome in {"blocked", "permission_denied"} else True
                                ),
                            },
                            "lpi_states": lpi_states,
                        }
                    )

    edge_cases = [
        ("Read", ["/workspace/project/packages/api/config.ts", "/workspace/project/packages/web/config.ts"], "success", "duplicate-basename"),
        ("Read", ["/Users/alice/.ssh/config"], "blocked", "home-redaction"),
        ("Write", ["/workspace/project/.env.production"], "permission_denied", "sensitive-name-no-content"),
        ("Grep", ["a-very-long-pattern-" + "x" * 180], "error", "bounded-length"),
    ]
    for tool, identifiers, outcome, label in edge_cases:
        sequence += 1
        proposed, normalized = reference_collapsed_renderer(
            tool,
            identifiers,
            outcome,
            workspace=workspace,
            max_length=max_length,
            multi_limit=multi_limit,
        )
        scenarios.append(
            {
                "scenario_id": f"edge-{sequence:03d}",
                "tool": tool,
                "cardinality": "single" if len(identifiers) == 1 else "multiple",
                "outcome": outcome,
                "variant": label,
                "identifiers": identifiers,
                "normalized_identifiers": normalized,
                "reported_collapsed_model": reported_collapsed_model(tool, identifiers, outcome),
                "reference_collapsed_output": proposed,
                "checks": {
                    "identifier_visible": all(
                        identifier_recognizable(proposed, value, max_length)
                        for value in normalized[:multi_limit]
                    ),
                    "outcome_visible": outcome == "success" or proposed.startswith(outcome_prefix(outcome)),
                    "workspace_private": not bool(re.search(r"/(?:Users|home)/[^/]+/", proposed)),
                    "content_safe": "\n" not in proposed,
                    "compact": len(proposed) <= max_length,
                    "critical_identifier_visible": (
                        all(
                            identifier_recognizable(proposed, value, max_length)
                            for value in normalized[:multi_limit]
                        )
                        if outcome in {"blocked", "permission_denied"}
                        else True
                    ),
                },
                "lpi_states": [
                    {"state": "Hello", "detail": {"tool": tool, "edge": label}},
                    {"state": "Mirror", "detail": {"normalized_identifiers": normalized}},
                    {"state": "Bind", "detail": {"outcome": outcome, "surface": "collapsed"}},
                    {"state": "Seal", "detail": {"checks": "see scenario checks"}},
                    {"state": "Flow", "detail": {"rendered": proposed}},
                ],
            }
        )
    return scenarios


def collision_metrics(scenarios: Iterable[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[str]] = defaultdict(list)
    for scenario in scenarios:
        groups[scenario[key]].append(scenario["scenario_id"])
    collisions = {value: ids for value, ids in groups.items() if len(ids) > 1}
    return {
        "unique_outputs": len(groups),
        "collision_groups": len(collisions),
        "colliding_scenarios": sum(len(ids) for ids in collisions.values()),
        "examples": [
            {"output": output, "scenario_ids": ids[:8]}
            for output, ids in list(sorted(collisions.items()))[:10]
        ],
    }


def matrix_summary(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scenarios)
    current_identifier_coverage = sum(
        any(identifier in scenario["reported_collapsed_model"] for identifier in scenario["normalized_identifiers"])
        for scenario in scenarios
    )
    contract_failures = [
        {
            "scenario_id": scenario["scenario_id"],
            "failed_checks": [name for name, passed in scenario["checks"].items() if not passed],
        }
        for scenario in scenarios
        if not all(scenario["checks"].values())
    ]
    critical = [scenario for scenario in scenarios if scenario["outcome"] in {"blocked", "permission_denied"}]
    return {
        "total_scenarios": total,
        "core_scenarios": len([item for item in scenarios if item["scenario_id"].startswith("core-")]),
        "edge_scenarios": len([item for item in scenarios if item["scenario_id"].startswith("edge-")]),
        "reported_model_identifier_coverage": {
            "passed": current_identifier_coverage,
            "total": total,
        },
        "reference_contract_identifier_coverage": {
            "passed": sum(item["checks"]["identifier_visible"] for item in scenarios),
            "total": total,
        },
        "critical_blocked_or_denied_identifier_coverage": {
            "passed": sum(item["checks"]["critical_identifier_visible"] for item in critical),
            "total": len(critical),
        },
        "reported_model_collisions": collision_metrics(scenarios, "reported_collapsed_model"),
        "reference_contract_collisions": collision_metrics(scenarios, "reference_collapsed_output"),
        "contract_failures": contract_failures,
        "contract_passed": not contract_failures,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tracker-head-sha", required=True)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target = config["target"]
    token = os.environ.get("GITHUB_TOKEN")
    issue, comments = fetch_issue_and_comments(target["repository"], int(target["issue_number"]), token)
    evidence = summarize_public_evidence(issue, comments)

    assignees = sorted(item.get("login") for item in issue.get("assignees", []) if item.get("login"))
    labels = sorted(item.get("name") for item in issue.get("labels", []) if item.get("name"))
    issue_snapshot = {
        "schema_version": "liminalqa-boris-issue-snapshot-v1",
        "observed_at": utc_now(),
        "repository": target["repository"],
        "issue_number": issue.get("number"),
        "html_url": issue.get("html_url"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "assignees": assignees,
        "labels": labels,
        "comments_reported": issue.get("comments"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "tracker_main_sha": args.tracker_head_sha,
        "tracker_boundary": "The public repository head is context only; it is not represented as the private TUI implementation source.",
        "public_evidence": evidence,
    }
    write_json(output / "issue-snapshot.json", issue_snapshot)

    scenarios = build_scenarios(config)
    summary = matrix_summary(scenarios)
    write_json(
        output / "render-matrix.json",
        {
            "schema_version": "liminalqa-primary-identifier-render-matrix-v1",
            "boundary": "Disclosed reference renderer derived from the public issue; not Claude Code product code.",
            "scenarios": scenarios,
            "summary": summary,
        },
    )
    write_json(
        output / "reference-contract.json",
        {
            "schema_version": "liminalqa-primary-identifier-contract-v1",
            "contract": config["contract"],
            "claim_boundary": config["claim_boundary"],
            "renderer_boundary": config["public_evidence_boundary"],
        },
    )

    required_labels = set(target["required_labels"])
    checks = [
        {"name": "issue_number_exact", "passed": issue.get("number") == target["issue_number"], "detail": issue.get("number")},
        {"name": "issue_state_expected", "passed": issue.get("state") == target["expected_state"], "detail": issue.get("state")},
        {"name": "boris_assigned", "passed": target["assignee"] in assignees, "detail": assignees},
        {"name": "required_labels_present", "passed": required_labels.issubset(labels), "detail": labels},
        {"name": "comments_complete", "passed": len(comments) >= int(issue.get("comments") or 0), "detail": {"fetched": len(comments), "reported_at_initial_snapshot": issue.get("comments")}},
        {"name": "public_demand_nontrivial", "passed": len(comments) >= 20 and evidence["unique_comment_authors"] >= 10, "detail": {"comments": len(comments), "authors": evidence["unique_comment_authors"]}},
        {"name": "regression_boundary_present", "passed": evidence["signal_counts"].get("regression_2_1_19_to_2_1_20", 0) > 0, "detail": evidence["signal_counts"].get("regression_2_1_19_to_2_1_20", 0)},
        {"name": "blocked_identifier_signal_present", "passed": evidence["signal_counts"].get("blocked_identifier_needed", 0) > 0, "detail": evidence["signal_counts"].get("blocked_identifier_needed", 0)},
        {"name": "reference_contract_passes", "passed": summary["contract_passed"], "detail": summary["contract_failures"]},
        {"name": "critical_identifier_coverage_complete", "passed": summary["critical_blocked_or_denied_identifier_coverage"]["passed"] == summary["critical_blocked_or_denied_identifier_coverage"]["total"], "detail": summary["critical_blocked_or_denied_identifier_coverage"]},
        {"name": "reported_abstraction_collides", "passed": summary["reported_model_collisions"]["collision_groups"] > 0, "detail": summary["reported_model_collisions"]},
        {"name": "reference_contract_reduces_collisions", "passed": summary["reference_contract_collisions"]["colliding_scenarios"] < summary["reported_model_collisions"]["colliding_scenarios"], "detail": {"reported": summary["reported_model_collisions"], "reference": summary["reference_contract_collisions"]}},
        {"name": "implementation_claim_blocked", "passed": config["public_evidence_boundary"]["implementation_claim_permitted"] is False, "detail": config["public_evidence_boundary"]},
    ]
    blocking = [item for item in checks if not item["passed"]]
    evidence_input = {
        "schema_version": "liminalqa-boris-primary-identifier-evidence-input-v1",
        "observed_at": utc_now(),
        "issue_snapshot_sha256": sha256_bytes((output / "issue-snapshot.json").read_bytes()),
        "render_matrix_sha256": sha256_bytes((output / "render-matrix.json").read_bytes()),
        "reference_contract_sha256": sha256_bytes((output / "reference-contract.json").read_bytes()),
        "issue_snapshot": issue_snapshot,
        "matrix_summary": summary,
        "checks": checks,
        "blocking_checks": blocking,
        "claim_boundary": config["claim_boundary"],
        "component_refs": config["component_refs"],
    }
    write_json(output / "boris-primary-identifier-evidence-input.json", evidence_input)

    summary_lines = [
        "# Boris / Claude Code #21151 primary-identifier evidence",
        "",
        f"- issue: `{target['repository']}#{target['issue_number']}`",
        f"- state: `{issue.get('state')}`",
        f"- assignees: `{', '.join(assignees)}`",
        f"- comments: `{len(comments)}` from `{evidence['unique_comment_authors']}` unique authors",
        f"- tracker main SHA: `{args.tracker_head_sha}`",
        f"- scenarios: `{summary['total_scenarios']}`",
        f"- reported-model identifier coverage: `{summary['reported_model_identifier_coverage']['passed']}/{summary['reported_model_identifier_coverage']['total']}`",
        f"- reference-contract identifier coverage: `{summary['reference_contract_identifier_coverage']['passed']}/{summary['reference_contract_identifier_coverage']['total']}`",
        f"- critical blocked/denied coverage: `{summary['critical_blocked_or_denied_identifier_coverage']['passed']}/{summary['critical_blocked_or_denied_identifier_coverage']['total']}`",
        f"- blocking checks: `{len(blocking)}`",
        "",
        "The renderer is a disclosed reference implementation. No Claude Code TUI source or installed runtime was inspected.",
        "",
    ]
    (output / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")
    print(json.dumps({"blocking": len(blocking), "summary": summary}, sort_keys=True))
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
