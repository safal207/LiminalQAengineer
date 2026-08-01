#!/usr/bin/env python3
"""Verify the cyber-causal guardrail replay inside the registered cargo CI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_VERDICT = "CONFIRMED_LOCAL_MECHANISM_REPRODUCTION_AND_GUARDRAIL_PASS"


def run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(args)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed


def git(repo: Path, *args: str) -> str:
    return run(["git", *args], cwd=repo).stdout.strip()


def assert_exact_sha(value: str, label: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise AssertionError(f"{label} is not an exact lowercase 40-character SHA")


def event_head_sha(repo: Path) -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        value = payload.get("pull_request", {}).get("head", {}).get("sha")
        if value:
            assert_exact_sha(value, "pull-request head")
            return value

    value = git(repo, "rev-parse", "HEAD")
    assert_exact_sha(value, "checked-out head")
    return value


def assert_checkout_binding(repo: Path, exact_head: str) -> str:
    checkout = git(repo, "rev-parse", "HEAD")
    assert_exact_sha(checkout, "checkout")
    if checkout == exact_head:
        return "EXACT_HEAD_CHECKOUT"

    workflow_sha = os.environ.get("GITHUB_SHA")
    if not workflow_sha:
        raise AssertionError("merge-ref checkout requires GITHUB_SHA binding")
    assert_exact_sha(workflow_sha, "workflow merge ref")
    if checkout != workflow_sha:
        raise AssertionError("checked-out merge ref does not match GITHUB_SHA")

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise AssertionError("merge-ref checkout requires GitHub event evidence")
    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    event_head = payload.get("pull_request", {}).get("head", {}).get("sha")
    if event_head != exact_head:
        raise AssertionError("GitHub event head does not match audited source identity")

    return "GITHUB_EVENT_BOUND_SHALLOW_MERGE_REF"


def assert_result(payload: dict[str, object], exact_head: str) -> None:
    expected = {
        "source_sha": exact_head,
        "authority": "LOCAL_DETERMINISTIC_SIMULATION_ONLY",
        "scenario_count": 8,
        "mechanism_scenario_count": 4,
        "mechanisms_reproduced": True,
        "all_guardrails_pass": True,
        "network_access": False,
        "credential_use": False,
        "external_mutation": False,
        "external_product_claim": "NONE",
        "verdict": REQUIRED_VERDICT,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise AssertionError(f"unexpected result field {key}: {payload.get(key)!r}")

    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 8:
        raise AssertionError("result must contain exactly eight scenarios")
    for scenario in scenarios:
        if scenario["guarded"]["invariant_pass"] is not True:
            raise AssertionError(f"guarded invariant failed: {scenario['scenario_id']}")
        if "vulnerable" in scenario and scenario["vulnerable"]["invariant_pass"] is not False:
            raise AssertionError(
                f"vulnerable mechanism did not reproduce: {scenario['scenario_id']}"
            )


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    exact_head = event_head_sha(repo)
    checkout_mode = assert_checkout_binding(repo, exact_head)

    clean_before = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if clean_before:
        raise AssertionError(f"worktree is not clean before replay:\n{clean_before}")

    test_env = os.environ.copy()
    test_env["PYTHONDONTWRITEBYTECODE"] = "1"
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests/test_cyber_causal_guardrail_replay.py",
            "-v",
        ],
        cwd=repo,
        env=test_env,
    )

    evidence = Path(tempfile.mkdtemp(prefix="cyber-causal-guardrail-"))
    try:
        result_path = evidence / "result.json"
        replay_path = evidence / "result-replay.json"
        manifest_path = evidence / "manifest.json"

        for output in (result_path, replay_path):
            run(
                [
                    sys.executable,
                    "scripts/cyber_causal_guardrail_replay.py",
                    "--source-sha",
                    exact_head,
                    "--output",
                    str(output),
                ],
                cwd=repo,
                env=test_env,
            )

        first = result_path.read_bytes()
        second = replay_path.read_bytes()
        if first != second:
            raise AssertionError("two replay outputs are not byte-identical")

        result = json.loads(first)
        assert_result(result, exact_head)

        run(
            [
                sys.executable,
                "scripts/write_cyber_guardrail_manifest.py",
                "--repository-root",
                ".",
                "--evidence-dir",
                str(evidence),
                "--expected-sha",
                exact_head,
                "--initial-sha",
                exact_head,
                "--final-sha",
                exact_head,
                "--output",
                str(manifest_path),
            ],
            cwd=repo,
            env=test_env,
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("expected_sha", "initial_sha", "final_sha"):
            if manifest.get(key) != exact_head:
                raise AssertionError(f"manifest identity mismatch: {key}")
        if manifest.get("byte_identical_replay") is not True:
            raise AssertionError("manifest did not bind byte-identical replay")
        if manifest.get("external_product_claim") != "NONE":
            raise AssertionError("manifest expanded external product claims")

        clean_after = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
        if clean_after:
            raise AssertionError(f"worktree is not clean after replay:\n{clean_after}")

        summary = {
            "exact_head": exact_head,
            "checkout_mode": checkout_mode,
            "scenario_count": result["scenario_count"],
            "mechanism_scenario_count": result["mechanism_scenario_count"],
            "verdict": result["verdict"],
            "result_sha256": manifest["result_sha256"],
            "file_count": manifest["file_count"],
            "network_access": False,
            "credential_use": False,
            "external_mutation": False,
            "external_product_claim": "NONE",
        }
        print(json.dumps(summary, sort_keys=True))
    finally:
        shutil.rmtree(evidence, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
