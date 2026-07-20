#!/usr/bin/env python3
"""Create exact public GitHub lifecycle evidence for Boris Cherny's open work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.github.com"

FORK_PRS = [
    {
        "fork_repo": "bcherny/openclaw",
        "fork_pr": 1,
        "fork_head": "1358cba9626af1be68e5788db217654864e05889",
        "upstream_repo": "openclaw/openclaw",
        "upstream_pr": 58036,
        "upstream_merge": "f6380ae4b7886f0cb5cc7dca45e9457017864c39",
    },
    {
        "fork_repo": "bcherny/openclaw",
        "fork_pr": 2,
        "fork_head": "2ca9eed4001ca20ad132f9b40df0b102c21fc879",
        "upstream_repo": "openclaw/openclaw",
        "upstream_pr": 58037,
        "upstream_merge": "bc16b9dccf87e662a966e2c49dfb5a6923ae4e88",
    },
    {
        "fork_repo": "bcherny/openclaw",
        "fork_pr": 3,
        "fork_head": "922344f985d05546cae1a39964666a8e76889157",
        "upstream_repo": "openclaw/openclaw",
        "upstream_pr": 58038,
        "upstream_merge": "af81c437fafc97808e17af771aa9fbfb0fff83b7",
    },
]

CLAUDE_ISSUES = [21151, 4937, 1554]
FOLLOWUP_SHA = "b474e098d15d8a0936153118adb6e28255b9071e"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_json(path: str) -> tuple[dict[str, Any], dict[str, str]]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "LiminalQAengineer-evidence/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{API}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            selected_headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower()
                in {
                    "etag",
                    "last-modified",
                    "x-ratelimit-limit",
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                }
            }
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {path} returned {error.code}: {body[:500]}") from error
    return json.loads(body), selected_headers


def sanitize_pr(pr: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    body = pr.get("body") or ""
    return {
        "number": pr["number"],
        "html_url": pr["html_url"],
        "state": pr["state"],
        "merged": bool(pr.get("merged")),
        "merge_commit_sha": pr.get("merge_commit_sha"),
        "head_sha": pr.get("head", {}).get("sha"),
        "base_sha": pr.get("base", {}).get("sha"),
        "title": pr.get("title"),
        "user": pr.get("user", {}).get("login"),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
        "closed_at": pr.get("closed_at"),
        "merged_at": pr.get("merged_at"),
        "body_sha256": sha256_text(body),
        "response_headers": headers,
    }


def sanitize_issue(issue: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    body = issue.get("body") or ""
    assignees = sorted(assignee.get("login") for assignee in issue.get("assignees", []))
    labels = sorted(label.get("name") for label in issue.get("labels", []))
    return {
        "number": issue["number"],
        "html_url": issue["html_url"],
        "state": issue["state"],
        "title": issue.get("title"),
        "user": issue.get("user", {}).get("login"),
        "assignees": assignees,
        "labels": labels,
        "comments": issue.get("comments"),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "body_sha256": sha256_text(body),
        "response_headers": headers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pr_pairs: list[dict[str, Any]] = []
    for expected in FORK_PRS:
        fork_raw, fork_headers = get_json(
            f"/repos/{expected['fork_repo']}/pulls/{expected['fork_pr']}"
        )
        upstream_raw, upstream_headers = get_json(
            f"/repos/{expected['upstream_repo']}/pulls/{expected['upstream_pr']}"
        )
        fork = sanitize_pr(fork_raw, fork_headers)
        upstream = sanitize_pr(upstream_raw, upstream_headers)
        checks = {
            "fork_is_open": fork["state"] == "open" and not fork["merged"],
            "fork_head_matches": fork["head_sha"] == expected["fork_head"],
            "upstream_is_merged": upstream["merged"] is True,
            "upstream_merge_matches": upstream["merge_commit_sha"]
            == expected["upstream_merge"],
            "same_author": fork["user"] == upstream["user"] == "bcherny",
            "same_title": fork["title"] == upstream["title"],
        }
        pr_pairs.append(
            {
                "expected": expected,
                "fork": fork,
                "upstream": upstream,
                "checks": checks,
                "verdict": "CLOSE_AS_SUPERSEDED"
                if all(checks.values())
                else "NEEDS_MANUAL_REVIEW",
            }
        )

    followup_raw, followup_headers = get_json(
        f"/repos/openclaw/openclaw/commits/{FOLLOWUP_SHA}"
    )
    followup_message = followup_raw.get("commit", {}).get("message", "")
    followup = {
        "sha": followup_raw.get("sha"),
        "html_url": followup_raw.get("html_url"),
        "message": followup_message,
        "message_sha256": sha256_text(followup_message),
        "response_headers": followup_headers,
        "checks": {
            "sha_matches": followup_raw.get("sha") == FOLLOWUP_SHA,
            "references_all_three": all(
                token in followup_message for token in ["#58036", "#58037", "#58038"]
            ),
            "states_overstatement_correction": "overstated prompt-cache comments"
            in followup_message,
        },
    }

    issues: list[dict[str, Any]] = []
    for issue_number in CLAUDE_ISSUES:
        raw, headers = get_json(
            f"/repos/anthropics/claude-code/issues/{issue_number}"
        )
        issue = sanitize_issue(raw, headers)
        checks = {
            "is_open": issue["state"] == "open",
            "assigned_to_bcherny": "bcherny" in issue["assignees"],
            "has_public_body": bool(issue["body_sha256"]),
        }
        issue["checks"] = checks
        issue["evidence_state"] = (
            "CURRENT_PUBLIC_ASSIGNED_ISSUE" if all(checks.values()) else "NEEDS_MANUAL_REVIEW"
        )
        issues.append(issue)

    all_prs_superseded = all(
        pair["verdict"] == "CLOSE_AS_SUPERSEDED" for pair in pr_pairs
    )
    followup_verified = all(followup["checks"].values())
    all_issues_current = all(
        issue["evidence_state"] == "CURRENT_PUBLIC_ASSIGNED_ISSUE"
        for issue in issues
    )

    result = {
        "schema_version": "liminalqa-boris-open-work-evidence-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "coordinate_model": {
            "O": "public GitHub REST resource + exact issue or PR number + observation time",
            "N": "read-only lifecycle observer",
            "T": "fork PR state -> upstream PR state -> follow-up correction -> assigned issue state",
        },
        "pull_request_pairs": pr_pairs,
        "upstream_followup": followup,
        "assigned_claude_code_issues": issues,
        "summary": {
            "fork_prs_verified_superseded": sum(
                pair["verdict"] == "CLOSE_AS_SUPERSEDED" for pair in pr_pairs
            ),
            "fork_prs_total": len(pr_pairs),
            "followup_verified": followup_verified,
            "assigned_issues_verified_current": sum(
                issue["evidence_state"] == "CURRENT_PUBLIC_ASSIGNED_ISSUE"
                for issue in issues
            ),
            "assigned_issues_total": len(issues),
            "verdict": "VERIFIED_OPEN_WORK_LIFECYCLE"
            if all_prs_superseded and followup_verified and all_issues_current
            else "PARTIAL_OR_CHANGED_LIFECYCLE",
        },
        "review_contracts": {
            "anthropics/claude-code#21151": "KEEP_OPEN_AND_DEFINE_VISIBLE_PRIMARY_IDENTIFIER_CONTRACT",
            "anthropics/claude-code#4937": "VERIFY_CURRENT_CLI_PARITY_THEN_CLOSE_OR_NARROW",
            "anthropics/claude-code#1554": "CURRENT_VERSION_REPRO_REQUIRED",
        },
        "boundaries": {
            "public_api_only": True,
            "read_only": True,
            "third_party_comments_posted_by_this_workflow": False,
            "third_party_state_modified": False,
            "private_data": False,
        },
        "authority": {
            "approval": False,
            "close": False,
            "assignment": False,
            "merge": False,
        },
    }

    result_path = output_dir / "boris-open-work-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Boris Cherny public open-work lifecycle evidence",
        "",
        f"- superseded fork PRs: `{result['summary']['fork_prs_verified_superseded']}/{result['summary']['fork_prs_total']}`",
        f"- upstream correction verified: `{str(followup_verified).lower()}`",
        f"- current assigned Claude Code issues: `{result['summary']['assigned_issues_verified_current']}/{result['summary']['assigned_issues_total']}`",
        f"- verdict: **{result['summary']['verdict']}**",
        "",
        "This is read-only evidence. The workflow does not close, approve, label, assign, or merge third-party work.",
        "",
    ]
    summary_path = output_dir / "boris-open-work-summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    checksums = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksums.append(f"{sha256_file(path)}  {path.name}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
