#!/usr/bin/env python3
"""Bounded deterministic evidence for gdb/tee-output#3.

The parent process launches isolated children. Each child imports the exact
installed tee-output source, writes unique records directly to fd 1 and fd 2,
then immediately closes the Tee. The patched counterfactual changes only the
shutdown protocol: flush, restore descriptors, close writers to deliver EOF,
wait naturally, and escalate only on timeout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def install_safe_shutdown_counterfactual() -> None:
    from tee_output import Tee

    def wait_naturally_then_escalate(proc: subprocess.Popen[Any], timeout: float = 5.0) -> dict[str, Any]:
        started = time.monotonic()
        escalation = "none"
        try:
            return_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            escalation = "terminate"
            proc.terminate()
            try:
                return_code = proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                escalation = "kill"
                proc.kill()
                return_code = proc.wait(timeout=2.0)
        return {
            "return_code": return_code,
            "escalation": escalation,
            "wait_ms": round((time.monotonic() - started) * 1000, 3),
        }

    def safe_close(self: Any) -> None:
        if getattr(self, "_liminalqa_closed", False):
            return
        self._liminalqa_closed = True

        # Flush Python wrappers while fd 1/fd 2 still target the tee pipes.
        sys.stdout.flush()
        sys.stderr.flush()

        # Stop future writes from entering the pipes.
        self.pause()

        pairs = [
            getattr(self, "stdout_pipe_proc", None),
            getattr(self, "stderr_pipe_proc", None),
        ]

        # Closing every writer first guarantees EOF can reach both tee readers.
        for pair in pairs:
            if pair is not None:
                pipe, _proc = pair
                if not pipe.closed:
                    pipe.close()

        waits: list[dict[str, Any]] = []
        for pair in pairs:
            if pair is not None:
                _pipe, proc = pair
                waits.append(wait_naturally_then_escalate(proc))

        self.stdout_pipe_proc = None
        self.stderr_pipe_proc = None
        self._liminalqa_waits = waits

    Tee.close = safe_close


def child_main(args: argparse.Namespace) -> int:
    if args.mode == "patched":
        install_safe_shutdown_counterfactual()

    from tee_output.tee import Tee

    round_dir = Path(args.round_dir)
    round_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = round_dir / "stdout.log"
    stderr_path = round_dir / "stderr.log"
    combined_path = round_dir / "combined.log"
    result_path = round_dir / "result.json"

    expected_stdout = [f"STDOUT:{index:06d}" for index in range(args.lines)]
    expected_stderr = [f"STDERR:{index:06d}" for index in range(args.lines)]

    tee = Tee()
    tee.to(
        stdout=[str(stdout_path), str(combined_path)],
        stderr=[str(stderr_path), str(combined_path)],
    )

    # os.write avoids Python buffering, isolating the reader-shutdown race.
    for stdout_record, stderr_record in zip(expected_stdout, expected_stderr, strict=True):
        os.write(sys.stdout.fileno(), f"{stdout_record}\n".encode("utf-8"))
        os.write(sys.stderr.fileno(), f"{stderr_record}\n".encode("utf-8"))

    started_close = time.monotonic()
    tee.close()
    close_ms = round((time.monotonic() - started_close) * 1000, 3)

    observed_stdout = safe_read_lines(stdout_path)
    observed_stderr = safe_read_lines(stderr_path)
    observed_combined = safe_read_lines(combined_path)

    stdout_set = set(observed_stdout)
    stderr_set = set(observed_stderr)
    combined_set = set(observed_combined)

    missing_stdout = [record for record in expected_stdout if record not in stdout_set]
    missing_stderr = [record for record in expected_stderr if record not in stderr_set]
    missing_combined = [
        record
        for record in [*expected_stdout, *expected_stderr]
        if record not in combined_set
    ]

    result = {
        "mode": args.mode,
        "round": args.round,
        "lines_per_stream": args.lines,
        "close_ms": close_ms,
        "stdout": {
            "expected": len(expected_stdout),
            "observed_lines": len(observed_stdout),
            "unique_expected_observed": len(stdout_set.intersection(expected_stdout)),
            "missing_count": len(missing_stdout),
            "missing_sample": missing_stdout[:20],
            "sha256": sha256_file(stdout_path) if stdout_path.exists() else None,
        },
        "stderr": {
            "expected": len(expected_stderr),
            "observed_lines": len(observed_stderr),
            "unique_expected_observed": len(stderr_set.intersection(expected_stderr)),
            "missing_count": len(missing_stderr),
            "missing_sample": missing_stderr[:20],
            "sha256": sha256_file(stderr_path) if stderr_path.exists() else None,
        },
        "combined": {
            "expected": len(expected_stdout) + len(expected_stderr),
            "observed_lines": len(observed_combined),
            "unique_expected_observed": len(
                combined_set.intersection([*expected_stdout, *expected_stderr])
            ),
            "missing_count": len(missing_combined),
            "missing_sample": missing_combined[:20],
            "sha256": sha256_file(combined_path) if combined_path.exists() else None,
        },
        "passed": not missing_stdout and not missing_stderr and not missing_combined,
        "counterfactual_waits": getattr(tee, "_liminalqa_waits", None),
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


def run_child(
    *,
    script: Path,
    mode: str,
    round_number: int,
    lines: int,
    output_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    round_dir = output_dir / mode / f"round-{round_number:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-u",
        str(script),
        "--child",
        "--mode",
        mode,
        "--round",
        str(round_number),
        "--round-dir",
        str(round_dir),
        "--lines",
        str(lines),
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        process = {
            "return_code": completed.returncode,
            "timed_out": False,
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
            "stdout_sha256": sha256_bytes(completed.stdout),
            "stderr_sha256": sha256_bytes(completed.stderr),
            "stdout_tail": completed.stdout.decode("utf-8", errors="replace")[-1000:],
            "stderr_tail": completed.stderr.decode("utf-8", errors="replace")[-1000:],
        }
    except subprocess.TimeoutExpired as error:
        process = {
            "return_code": None,
            "timed_out": True,
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
            "stdout_sha256": sha256_bytes(error.stdout or b""),
            "stderr_sha256": sha256_bytes(error.stderr or b""),
            "stdout_tail": (error.stdout or b"").decode("utf-8", errors="replace")[-1000:],
            "stderr_tail": (error.stderr or b"").decode("utf-8", errors="replace")[-1000:],
        }

    result_path = round_dir / "result.json"
    child_result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.exists()
        else None
    )
    return {"process": process, "result": child_result}


def aggregate_main(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()

    source_path = Path(args.source_file)
    source_text = source_path.read_text(encoding="utf-8")
    static_observation = {
        "source_file": str(source_path),
        "source_sha256": sha256_file(source_path),
        "close_calls_pause_before_drain": "self.pause()\n        self._drain" in source_text,
        "drain_sends_sigint_before_wait": "os.kill(proc.pid, signal.SIGINT)" in source_text,
        "close_flushes_stdout": "sys.stdout.flush()" in source_text,
        "close_flushes_stderr": "sys.stderr.flush()" in source_text,
    }

    baseline = [
        run_child(
            script=script,
            mode="baseline",
            round_number=index,
            lines=args.lines,
            output_dir=output_dir,
            timeout=args.timeout,
        )
        for index in range(1, args.baseline_rounds + 1)
    ]
    patched = [
        run_child(
            script=script,
            mode="patched",
            round_number=index,
            lines=args.lines,
            output_dir=output_dir,
            timeout=args.timeout,
        )
        for index in range(1, args.patched_rounds + 1)
    ]

    def failures(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            entry
            for entry in entries
            if entry["process"]["timed_out"]
            or entry["process"]["return_code"] != 0
            or not entry.get("result")
            or not entry["result"].get("passed", False)
        ]

    baseline_failures = failures(baseline)
    patched_failures = failures(patched)

    if baseline_failures and not patched_failures:
        verdict = "CONFIRMED_SHUTDOWN_DATA_LOSS_WITH_PASSING_COUNTERFACTUAL"
    elif baseline_failures:
        verdict = "BASELINE_FAILURE_CONFIRMED_COUNTERFACTUAL_INCONCLUSIVE"
    elif not patched_failures:
        verdict = "NOT_REPRODUCED_ON_THIS_RUN_COUNTERFACTUAL_PASSES"
    else:
        verdict = "INCONCLUSIVE"

    result = {
        "schema_version": "liminalqa-greg-tee-output-evidence-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "upstream": {
            "repository": "gdb/tee-output",
            "exact_sha": args.upstream_sha,
            "issue": "https://github.com/gdb/tee-output/issues/3",
        },
        "coordinate_model": {
            "O": "exact source SHA + Linux runner + Python version + immediate shutdown",
            "N": "isolated child process writing unique records directly to fd 1 and fd 2",
            "T": "redirect -> bounded writes -> immediate close -> file verification",
            "counterfactual": "same source and writes; shutdown protocol only is replaced",
        },
        "parameters": {
            "lines_per_stream": args.lines,
            "baseline_rounds": args.baseline_rounds,
            "patched_rounds": args.patched_rounds,
            "child_timeout_seconds": args.timeout,
            "python": sys.version,
            "platform": sys.platform,
        },
        "static_observation": static_observation,
        "baseline": baseline,
        "patched_counterfactual": patched,
        "summary": {
            "baseline_failure_rounds": len(baseline_failures),
            "baseline_total_rounds": len(baseline),
            "patched_failure_rounds": len(patched_failures),
            "patched_total_rounds": len(patched),
            "verdict": verdict,
        },
        "boundaries": {
            "public_source_only": True,
            "local_processes_only": True,
            "network_during_reproducer": False,
            "third_party_repository_modified": False,
            "production_system_tested": False,
            "load_test": False,
        },
        "authority": {
            "mode": "evidence_only",
            "external_fix_applied": False,
            "approval": False,
            "merge": False,
        },
    }

    result_path = output_dir / "greg-tee-output-result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    summary = "\n".join(
        [
            "# gdb/tee-output#3 deterministic shutdown evidence",
            "",
            f"- exact upstream SHA: `{args.upstream_sha}`",
            f"- lines per stream per round: `{args.lines}`",
            f"- baseline failures: `{len(baseline_failures)}/{len(baseline)}`",
            f"- safe-shutdown counterfactual failures: `{len(patched_failures)}/{len(patched)}`",
            f"- verdict: **{verdict}**",
            "",
            "The counterfactual changes only shutdown ordering: flush wrappers, restore fd 1/fd 2, close pipe writers to deliver EOF, wait naturally, and terminate only after a timeout.",
            "",
            "No remote service, account, production process, or third-party repository was modified.",
            "",
        ]
    )
    summary_path = output_dir / "greg-tee-output-summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    checksums = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name not in {"SHA256SUMS.txt"}:
            checksums.append(f"{sha256_file(path)}  {path.relative_to(output_dir)}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    print(summary)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--mode", choices=["baseline", "patched"])
    parser.add_argument("--round", type=int, default=0)
    parser.add_argument("--round-dir")
    parser.add_argument("--lines", type=int, default=5000)
    parser.add_argument("--output-dir")
    parser.add_argument("--source-file")
    parser.add_argument("--upstream-sha", default="c41f8ff383200320b746e953e92709ae1b505a71")
    parser.add_argument("--baseline-rounds", type=int, default=12)
    parser.add_argument("--patched-rounds", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.child:
        if not args.mode or not args.round_dir:
            raise SystemExit("--child requires --mode and --round-dir")
        return child_main(args)
    if not args.output_dir or not args.source_file:
        raise SystemExit("aggregate mode requires --output-dir and --source-file")
    return aggregate_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
