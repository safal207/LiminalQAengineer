#!/usr/bin/env python3
"""Cross-platform bounded evidence for gdb/tee-output#3.

The runner executes the original issue-shaped print/traceback trajectory and a
buffer-independent os.write trajectory on Linux and macOS, with and without a
PTY.  A counterfactual changes only shutdown ordering.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import platform
import pty
import select
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def event(events: list[dict[str, Any]], name: str, **details: Any) -> None:
    events.append(
        {
            "sequence": len(events) + 1,
            "name": name,
            "wall_time_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            "details": details,
        }
    )


def install_safe_shutdown_counterfactual() -> None:
    from tee_output import Tee

    def wait_naturally_then_escalate(
        proc: subprocess.Popen[Any], timeout: float = 5.0
    ) -> dict[str, Any]:
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
        sys.stdout.flush()
        sys.stderr.flush()
        self.pause()
        pairs = [
            getattr(self, "stdout_pipe_proc", None),
            getattr(self, "stderr_pipe_proc", None),
        ]
        for pair in pairs:
            if pair is not None:
                pipe, _proc = pair
                if not pipe.closed:
                    pipe.close()
        waits = []
        for pair in pairs:
            if pair is not None:
                _pipe, proc = pair
                waits.append(wait_naturally_then_escalate(proc))
        self.stdout_pipe_proc = None
        self.stderr_pipe_proc = None
        self._liminalqa_waits = waits

    Tee.close = safe_close


def child_main(args: argparse.Namespace) -> int:
    if args.shutdown == "patched":
        install_safe_shutdown_counterfactual()

    from tee_output import Tee

    round_dir = Path(args.round_dir)
    round_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = round_dir / "stdout.log"
    stderr_path = round_dir / "stderr.log"
    combined_path = round_dir / "combined.log"
    result_path = round_dir / "child-result.json"
    events: list[dict[str, Any]] = []

    coordinate = {
        "scenario": args.scenario,
        "pty": bool(args.pty),
        "delay_ms": args.delay_ms,
        "shutdown": args.shutdown,
        "round": args.round,
    }
    event(events, "RUN_CREATED", coordinate=coordinate)
    before_isatty = {"stdout": sys.stdout.isatty(), "stderr": sys.stderr.isatty()}
    event(events, "OBSERVER_BOUND", isatty=before_isatty)

    tee = Tee()
    event(events, "TEE_CREATED")
    tee.to(
        stdout=[str(stdout_path), str(combined_path)],
        stderr=[str(stderr_path), str(combined_path)],
    )
    event(events, "REDIRECT_ACTIVE")

    expected_stdout: list[str] = []
    expected_stderr: list[str] = []
    expected_stderr_substrings: list[str] = []

    if args.scenario == "issue":
        stdout_marker = f"ISSUE-STDOUT:{args.round:04d}"
        stderr_marker = f"ISSUE-STDERR:{args.round:04d}"
        assertion_marker = f"liminalqa-{args.round:04d}"
        expected_stdout = [stdout_marker]
        expected_stderr = [stderr_marker]
        expected_stderr_substrings = ["Traceback (most recent call last):", f"AssertionError: {assertion_marker}"]
        print(stdout_marker)
        print(stderr_marker, file=sys.stderr)
        event(events, "ISSUE_MARKERS_WRITTEN")
        try:
            raise AssertionError(assertion_marker)
        except AssertionError:
            traceback.print_exc()
        event(events, "TRACEBACK_WRITTEN")
    else:
        expected_stdout = [f"STDOUT:{index:06d}" for index in range(args.lines)]
        expected_stderr = [f"STDERR:{index:06d}" for index in range(args.lines)]
        for stdout_record, stderr_record in zip(expected_stdout, expected_stderr, strict=True):
            os.write(sys.stdout.fileno(), f"{stdout_record}\n".encode("utf-8"))
            os.write(sys.stderr.fileno(), f"{stderr_record}\n".encode("utf-8"))
        event(events, "FD_RECORDS_WRITTEN", lines_per_stream=args.lines)

    if args.delay_ms:
        time.sleep(args.delay_ms / 1000.0)
    event(events, "CLOSE_REQUESTED", delay_ms=args.delay_ms)
    close_started = time.monotonic()
    tee.close()
    close_ms = round((time.monotonic() - close_started) * 1000, 3)
    event(events, "CLOSE_COMPLETED", close_ms=close_ms)

    stdout_text = read_text(stdout_path)
    stderr_text = read_text(stderr_path)
    combined_text = read_text(combined_path)
    event(events, "FILES_OBSERVED")

    missing_stdout = [value for value in expected_stdout if value not in stdout_text]
    missing_stderr = [value for value in expected_stderr if value not in stderr_text]
    missing_stderr_substrings = [
        value for value in expected_stderr_substrings if value not in stderr_text
    ]
    missing_combined = [
        value
        for value in [*expected_stdout, *expected_stderr, *expected_stderr_substrings]
        if value not in combined_text
    ]
    passed = not (
        missing_stdout
        or missing_stderr
        or missing_stderr_substrings
        or missing_combined
    )
    event(events, "VERIFICATION_COMPLETED", passed=passed)

    result = {
        "schema_version": "liminalqa-greg-tee-platform-child-v1",
        "coordinate": coordinate,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
            "isatty_before_redirect": before_isatty,
        },
        "close_ms": close_ms,
        "verification": {
            "passed": passed,
            "missing_stdout": missing_stdout[:20],
            "missing_stderr": missing_stderr[:20],
            "missing_stderr_substrings": missing_stderr_substrings,
            "missing_combined": missing_combined[:20],
        },
        "files": {
            "stdout": {"bytes": len(stdout_text.encode()), "sha256": sha256_file(stdout_path)},
            "stderr": {"bytes": len(stderr_text.encode()), "sha256": sha256_file(stderr_path)},
            "combined": {"bytes": len(combined_text.encode()), "sha256": sha256_file(combined_path)},
        },
        "counterfactual_waits": getattr(tee, "_liminalqa_waits", None),
        "events": events,
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


def run_with_pty(command: list[str], timeout: float) -> dict[str, Any]:
    master_fd, slave_fd = pty.openpty()
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)
    output = bytearray()
    timed_out = False
    deadline = started + timeout
    try:
        while True:
            if time.monotonic() > deadline:
                timed_out = True
                process.kill()
                break
            ready, _, _ = select.select([master_fd], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(master_fd, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output.extend(chunk)
            if process.poll() is not None and not ready:
                try:
                    while True:
                        chunk = os.read(master_fd, 65536)
                        if not chunk:
                            break
                        output.extend(chunk)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                break
        return_code = process.wait(timeout=2)
    finally:
        os.close(master_fd)
    return {
        "return_code": return_code,
        "timed_out": timed_out,
        "wall_ms": round((time.monotonic() - started) * 1000, 3),
        "terminal_sha256": sha256_bytes(bytes(output)),
        "terminal_tail": bytes(output).decode("utf-8", errors="replace")[-1500:],
    }


def run_child(
    *,
    script: Path,
    scenario: str,
    pty_mode: bool,
    delay_ms: int,
    shutdown: str,
    round_number: int,
    lines: int,
    output_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    coordinate_name = f"{scenario}-pty-{int(pty_mode)}-delay-{delay_ms}-{shutdown}"
    round_dir = output_dir / "rounds" / coordinate_name / f"round-{round_number:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-u",
        str(script),
        "--child",
        "--scenario",
        scenario,
        "--shutdown",
        shutdown,
        "--round",
        str(round_number),
        "--round-dir",
        str(round_dir),
        "--lines",
        str(lines),
        "--delay-ms",
        str(delay_ms),
    ]
    if pty_mode:
        command.append("--pty")
        process = run_with_pty(command, timeout)
    else:
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
            }
    result_path = round_dir / "child-result.json"
    child_result = json.loads(result_path.read_text()) if result_path.exists() else None
    return {"process": process, "result": child_result}


def aggregate_main(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    source_path = Path(args.source_file)
    source_text = source_path.read_text(encoding="utf-8")

    entries: list[dict[str, Any]] = []
    for scenario in ("issue", "fd"):
        for pty_mode in (False, True):
            for delay_ms in args.delays:
                for shutdown in ("baseline", "patched"):
                    for round_number in range(1, args.rounds + 1):
                        entries.append(
                            run_child(
                                script=script,
                                scenario=scenario,
                                pty_mode=pty_mode,
                                delay_ms=delay_ms,
                                shutdown=shutdown,
                                round_number=round_number,
                                lines=args.lines,
                                output_dir=output_dir,
                                timeout=args.timeout,
                            )
                        )

    coordinates: dict[str, dict[str, Any]] = {}
    all_events: list[dict[str, Any]] = []
    for entry in entries:
        result = entry.get("result")
        if result:
            coordinate = result["coordinate"]
            key = "|".join(
                [
                    coordinate["scenario"],
                    f"pty={int(coordinate['pty'])}",
                    f"delay={coordinate['delay_ms']}",
                    coordinate["shutdown"],
                ]
            )
        else:
            key = "missing-result"
        bucket = coordinates.setdefault(
            key,
            {"total": 0, "failures": 0, "timeouts": 0, "samples": []},
        )
        bucket["total"] += 1
        failed = (
            entry["process"].get("timed_out")
            or entry["process"].get("return_code") != 0
            or not result
            or not result["verification"]["passed"]
        )
        if failed:
            bucket["failures"] += 1
            bucket["samples"].append(entry)
        if entry["process"].get("timed_out"):
            bucket["timeouts"] += 1
        if result:
            for child_event in result["events"]:
                all_events.append(
                    {
                        "coordinate": result["coordinate"],
                        "platform": result["platform"],
                        **child_event,
                    }
                )

    baseline_failures = sum(
        bucket["failures"] for key, bucket in coordinates.items() if key.endswith("|baseline")
    )
    patched_failures = sum(
        bucket["failures"] for key, bucket in coordinates.items() if key.endswith("|patched")
    )
    timeouts = sum(bucket["timeouts"] for bucket in coordinates.values())
    if timeouts:
        verdict = "BLOCKED_TIMEOUTS"
    elif baseline_failures and not patched_failures:
        verdict = "DATA_LOSS_OBSERVED_WITH_PASSING_SHUTDOWN_COUNTERFACTUAL"
    elif baseline_failures and patched_failures:
        verdict = "DATA_LOSS_OBSERVED_COUNTERFACTUAL_INCONCLUSIVE"
    elif not patched_failures:
        verdict = "NOT_REPRODUCED_ON_THIS_PLATFORM_STATIC_RISK_REMAINS"
    else:
        verdict = "INCONCLUSIVE"

    result = {
        "schema_version": "liminalqa-greg-tee-platform-evidence-v2",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "upstream": {
            "repository": "gdb/tee-output",
            "issue": 3,
            "exact_sha": args.upstream_sha,
            "source_file_sha256": sha256_file(source_path),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "matrix": {
            "scenarios": ["issue", "fd"],
            "pty_modes": [False, True],
            "delay_ms": args.delays,
            "shutdown_modes": ["baseline", "patched"],
            "rounds_per_coordinate": args.rounds,
            "fd_lines_per_stream": args.lines,
        },
        "static_observation": {
            "pause_before_drain": "self.pause()\n        self._drain" in source_text,
            "sigint_before_wait": "os.kill(proc.pid, signal.SIGINT)" in source_text,
            "explicit_stdout_flush": "sys.stdout.flush()" in source_text,
            "explicit_stderr_flush": "sys.stderr.flush()" in source_text,
        },
        "coordinates": coordinates,
        "summary": {
            "child_runs": len(entries),
            "baseline_failures": baseline_failures,
            "patched_failures": patched_failures,
            "timeouts": timeouts,
            "verdict": verdict,
        },
        "authority": {
            "mode": "read_only_evidence",
            "external_state_change": False,
            "approval": False,
            "close": False,
            "merge": False,
        },
    }
    (output_dir / "greg-platform-result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "greg-platform-events.jsonl").open("w", encoding="utf-8") as handle:
        for item in sorted(all_events, key=lambda value: (value["wall_time_ns"], value["monotonic_ns"])):
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    summary = "\n".join(
        [
            f"# Greg tee-output cross-platform evidence — {platform.system()}",
            "",
            f"- child runs: `{len(entries)}`",
            f"- baseline failures: `{baseline_failures}`",
            f"- patched failures: `{patched_failures}`",
            f"- timeouts: `{timeouts}`",
            f"- verdict: **{verdict}**",
            "",
        ]
    )
    (output_dir / "greg-platform-summary.md").write_text(summary, encoding="utf-8")
    checksums = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            checksums.append(f"{sha256_file(path)}  {path.relative_to(output_dir)}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
    print(summary)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--scenario", choices=["issue", "fd"])
    parser.add_argument("--shutdown", choices=["baseline", "patched"])
    parser.add_argument("--pty", action="store_true")
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--round", type=int, default=0)
    parser.add_argument("--round-dir")
    parser.add_argument("--lines", type=int, default=64)
    parser.add_argument("--output-dir")
    parser.add_argument("--source-file")
    parser.add_argument("--upstream-sha", default="c41f8ff383200320b746e953e92709ae1b505a71")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--delays", type=int, nargs="+", default=[0, 1, 10, 100])
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.child:
        if not args.scenario or not args.shutdown or not args.round_dir:
            raise SystemExit("child mode requires scenario, shutdown and round-dir")
        return child_main(args)
    if not args.output_dir or not args.source_file:
        raise SystemExit("aggregate mode requires output-dir and source-file")
    return aggregate_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
