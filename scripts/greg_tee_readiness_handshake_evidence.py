#!/usr/bin/env python3
"""Readiness-handshake counterfactual for gdb/tee-output#3.

The experiment keeps the exact upstream tee-output implementation and compares:

* current: write immediately after Tee.to()
* sleep100: fixed 100 ms delay
* file_exists: wait until all output paths exist
* supervisor_ack: wrap the real system tee, wait until it is alive and has opened
  all output files, then emit an acknowledgement before writes are allowed
* supervisor_ack_safe_close: the same acknowledgement plus a shutdown-order
  counterfactual

The wrapper still launches the real system ``tee`` under ``parent-lifetime``.
The acknowledgement is supervisory, not an internal proof that tee reached a
specific source-code read-loop instruction.
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
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

MODES = (
    "current",
    "sleep100",
    "file_exists",
    "supervisor_ack",
    "supervisor_ack_safe_close",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


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


def relay_main(args: argparse.Namespace) -> int:
    """Run the real system tee and emit a supervisory readiness acknowledgement."""

    command = list(args.relay_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("relay command is required")
    try:
        marker = command.index("-a")
    except ValueError as exc:
        raise SystemExit("relay command must contain tee -a") from exc
    targets = [Path(item) for item in command[marker + 1 :]]
    ready_path = Path(args.ready_file)
    started_wall = time.time_ns()
    started_mono = time.monotonic_ns()

    child = subprocess.Popen(command)
    deadline = time.monotonic() + args.ready_timeout
    condition = "timeout"
    while time.monotonic() < deadline:
        if child.poll() is not None:
            condition = "child_exited_before_ready"
            break
        if targets and all(path.exists() for path in targets):
            condition = "child_alive_and_all_targets_exist"
            break
        time.sleep(0.0005)

    acknowledgement = {
        "schema_version": "liminalqa-tee-supervisor-ack-v1",
        "condition": condition,
        "relay_pid": os.getpid(),
        "tee_pid": child.pid,
        "command": command,
        "targets": [str(path) for path in targets],
        "started_wall_time_ns": started_wall,
        "started_monotonic_ns": started_mono,
        "ack_wall_time_ns": time.time_ns(),
        "ack_monotonic_ns": time.monotonic_ns(),
        "latency_ms": round((time.monotonic_ns() - started_mono) / 1_000_000, 3),
        "child_alive": child.poll() is None,
        "all_targets_exist": bool(targets) and all(path.exists() for path in targets),
    }
    write_json(ready_path, acknowledgement)

    if condition != "child_alive_and_all_targets_exist":
        if child.poll() is None:
            child.terminate()
        try:
            return child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            return child.wait(timeout=2)
    return child.wait()


def install_supervisor_wrapper(
    *,
    script: Path,
    round_dir: Path,
) -> tuple[list[Path], Callable[[], None]]:
    """Rewrite only the upstream parent-lifetime -> tee command."""

    import tee_output

    original = tee_output.subprocess.Popen
    ready_files: list[Path] = []
    counter = 0

    def wrapped_popen(command: Any, *popen_args: Any, **popen_kwargs: Any) -> Any:
        nonlocal counter
        if (
            isinstance(command, list)
            and len(command) >= 5
            and command[0] == "parent-lifetime"
            and command[1] == "--term"
            and command[2] == "tee"
            and command[3] == "-a"
        ):
            counter += 1
            ready_path = round_dir / f"supervisor-ready-{counter}.json"
            ready_files.append(ready_path)
            rewritten = [
                "parent-lifetime",
                "--term",
                sys.executable,
                str(script),
                "--relay",
                "--ready-file",
                str(ready_path),
                "--ready-timeout",
                "5",
                "--",
                *command[2:],
            ]
            return original(rewritten, *popen_args, **popen_kwargs)
        return original(command, *popen_args, **popen_kwargs)

    tee_output.subprocess.Popen = wrapped_popen

    def restore() -> None:
        tee_output.subprocess.Popen = original

    return ready_files, restore


def wait_for_paths(paths: list[Path], timeout: float) -> dict[str, Any]:
    started = time.monotonic_ns()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(path.exists() for path in paths):
            return {
                "passed": True,
                "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
                "paths": [str(path) for path in paths],
            }
        time.sleep(0.0005)
    return {
        "passed": False,
        "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
        "paths": [str(path) for path in paths],
        "existing": [str(path) for path in paths if path.exists()],
    }


def wait_for_acknowledgements(paths: list[Path], timeout: float) -> dict[str, Any]:
    started = time.monotonic_ns()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if paths and all(path.exists() for path in paths):
            values = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            passed = all(
                value.get("condition") == "child_alive_and_all_targets_exist"
                and value.get("child_alive")
                and value.get("all_targets_exist")
                for value in values
            )
            return {
                "passed": passed,
                "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
                "acknowledgements": values,
            }
        time.sleep(0.0005)
    return {
        "passed": False,
        "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
        "expected_ack_files": [str(path) for path in paths],
        "existing_ack_files": [str(path) for path in paths if path.exists()],
    }


def child_main(args: argparse.Namespace) -> int:
    from tee_output import Tee

    round_dir = Path(args.round_dir)
    round_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = round_dir / "stdout.log"
    stderr_path = round_dir / "stderr.log"
    combined_path = round_dir / "combined.log"
    result_path = round_dir / "child-result.json"
    script = Path(__file__).resolve()
    events: list[dict[str, Any]] = []
    trace_id = f"greg-ready-{uuid.uuid4()}"

    coordinate = {
        "scenario": args.scenario,
        "pty": bool(args.pty),
        "mode": args.mode,
        "round": args.round,
    }
    event(events, "SENSE_RUN_CREATED", trace_id=trace_id, coordinate=coordinate)
    before_isatty = {"stdout": sys.stdout.isatty(), "stderr": sys.stderr.isatty()}
    event(events, "SENSE_OBSERVER_BOUND", isatty=before_isatty)

    ready_files: list[Path] = []
    restore_wrapper: Callable[[], None] | None = None
    if args.mode in {"supervisor_ack", "supervisor_ack_safe_close"}:
        ready_files, restore_wrapper = install_supervisor_wrapper(
            script=script,
            round_dir=round_dir,
        )
        event(events, "TRANSITION_LPI_HELLO", mode=args.mode)
    if args.mode == "supervisor_ack_safe_close":
        install_safe_shutdown_counterfactual()
        event(events, "TRANSITION_SAFE_CLOSE_INSTALLED")

    tee = Tee()
    event(events, "TRANSITION_TEE_CREATED")
    tee.to(
        stdout=[str(stdout_path), str(combined_path)],
        stderr=[str(stderr_path), str(combined_path)],
    )
    event(
        events,
        "TRANSITION_REDIRECT_ACTIVE",
        stdout_proc=getattr(getattr(tee, "stdout_pipe_proc", (None, None))[1], "pid", None),
        stderr_proc=getattr(getattr(tee, "stderr_pipe_proc", (None, None))[1], "pid", None),
    )

    gate: dict[str, Any] = {"mode": args.mode, "passed": True}
    if args.mode == "sleep100":
        started = time.monotonic_ns()
        time.sleep(0.1)
        gate.update(
            {
                "kind": "fixed_delay",
                "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
            }
        )
        event(events, "TRANSITION_CAPU_INCUBATE_COMPLETE", gate=gate)
    elif args.mode == "file_exists":
        gate = {"mode": args.mode, "kind": "file_exists", **wait_for_paths(
            [stdout_path, stderr_path, combined_path],
            timeout=args.ready_timeout,
        )}
        event(events, "TRANSITION_FILE_EXISTENCE_OBSERVED", gate=gate)
    elif args.mode in {"supervisor_ack", "supervisor_ack_safe_close"}:
        gate = {
            "mode": args.mode,
            "kind": "supervisor_ack",
            **wait_for_acknowledgements(ready_files, timeout=args.ready_timeout),
        }
        event(events, "TRANSITION_LPI_SEAL_RECEIVED", gate=gate)
    else:
        event(events, "TRANSITION_NO_READINESS_BARRIER")

    if gate.get("passed", True):
        event(events, "COMMIT_CAPU_WRITE_GATE_OPENED", mode=args.mode)
    else:
        event(events, "COMMIT_CAPU_WRITE_GATE_REJECTED", mode=args.mode)

    expected_stdout: list[str] = []
    expected_stderr: list[str] = []
    expected_stderr_substrings: list[str] = []

    if gate.get("passed", True):
        if args.scenario == "issue":
            stdout_marker = f"ISSUE-STDOUT:{args.round:04d}"
            stderr_marker = f"ISSUE-STDERR:{args.round:04d}"
            assertion_marker = f"liminalqa-ready-{args.round:04d}"
            expected_stdout = [stdout_marker]
            expected_stderr = [stderr_marker]
            expected_stderr_substrings = [
                "Traceback (most recent call last):",
                f"AssertionError: {assertion_marker}",
            ]
            print(stdout_marker)
            print(stderr_marker, file=sys.stderr)
            try:
                raise AssertionError(assertion_marker)
            except AssertionError:
                traceback.print_exc()
            event(events, "TRANSITION_FLOW_ISSUE_PAYLOAD_WRITTEN")
        else:
            expected_stdout = [f"STDOUT:{index:06d}" for index in range(args.lines)]
            expected_stderr = [f"STDERR:{index:06d}" for index in range(args.lines)]
            for stdout_record, stderr_record in zip(expected_stdout, expected_stderr, strict=True):
                os.write(sys.stdout.fileno(), f"{stdout_record}\n".encode("utf-8"))
                os.write(sys.stderr.fileno(), f"{stderr_record}\n".encode("utf-8"))
            event(events, "TRANSITION_FLOW_FD_PAYLOAD_WRITTEN", lines_per_stream=args.lines)

    event(events, "TRANSITION_CLOSE_REQUESTED")
    close_started = time.monotonic()
    tee.close()
    close_ms = round((time.monotonic() - close_started) * 1000, 3)
    event(events, "TRANSITION_CLOSE_COMPLETED", close_ms=close_ms)

    if restore_wrapper is not None:
        restore_wrapper()

    stdout_text = read_text(stdout_path)
    stderr_text = read_text(stderr_path)
    combined_text = read_text(combined_path)
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
    passed = bool(gate.get("passed", True)) and not (
        missing_stdout
        or missing_stderr
        or missing_stderr_substrings
        or missing_combined
    )
    event(events, "COMMIT_OUTPUT_VERIFIED", passed=passed)

    result = {
        "schema_version": "liminalqa-greg-tee-readiness-child-v1",
        "trace_id": trace_id,
        "coordinate": coordinate,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
            "isatty_before_redirect": before_isatty,
        },
        "gate": gate,
        "close_ms": close_ms,
        "verification": {
            "passed": passed,
            "missing_stdout": missing_stdout[:20],
            "missing_stderr": missing_stderr[:20],
            "missing_stderr_substrings": missing_stderr_substrings,
            "missing_combined": missing_combined[:20],
        },
        "files": {
            "stdout": {"exists": stdout_path.exists(), "bytes": len(stdout_text.encode()), "sha256": sha256_file(stdout_path)},
            "stderr": {"exists": stderr_path.exists(), "bytes": len(stderr_text.encode()), "sha256": sha256_file(stderr_path)},
            "combined": {"exists": combined_path.exists(), "bytes": len(combined_text.encode()), "sha256": sha256_file(combined_path)},
        },
        "counterfactual_waits": getattr(tee, "_liminalqa_waits", None),
        "events": events,
    }
    write_json(result_path, result)
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
    mode: str,
    round_number: int,
    lines: int,
    output_dir: Path,
    timeout: float,
    ready_timeout: float,
) -> dict[str, Any]:
    coordinate_name = f"{scenario}-pty-{int(pty_mode)}-{mode}"
    round_dir = output_dir / "rounds" / coordinate_name / f"round-{round_number:02d}"
    round_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-u",
        str(script),
        "--child",
        "--scenario",
        scenario,
        "--mode",
        mode,
        "--round",
        str(round_number),
        "--round-dir",
        str(round_dir),
        "--lines",
        str(lines),
        "--ready-timeout",
        str(ready_timeout),
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
            for mode in MODES:
                for round_number in range(1, args.rounds + 1):
                    entries.append(
                        run_child(
                            script=script,
                            scenario=scenario,
                            pty_mode=pty_mode,
                            mode=mode,
                            round_number=round_number,
                            lines=args.lines,
                            output_dir=output_dir,
                            timeout=args.timeout,
                            ready_timeout=args.ready_timeout,
                        )
                    )

    coordinates: dict[str, dict[str, Any]] = {}
    timeouts = 0
    missing_results = 0
    for entry in entries:
        process = entry["process"]
        child = entry["result"]
        if process.get("timed_out"):
            timeouts += 1
        if child is None:
            missing_results += 1
            continue
        coordinate = child["coordinate"]
        key = (
            f'{coordinate["scenario"]}|pty={int(coordinate["pty"])}|'
            f'{coordinate["mode"]}'
        )
        bucket = coordinates.setdefault(
            key,
            {
                "scenario": coordinate["scenario"],
                "pty": coordinate["pty"],
                "mode": coordinate["mode"],
                "total": 0,
                "failures": 0,
                "gate_failures": 0,
                "gate_latency_ms": [],
                "close_ms": [],
            },
        )
        bucket["total"] += 1
        if not child["verification"]["passed"]:
            bucket["failures"] += 1
        if not child["gate"].get("passed", True):
            bucket["gate_failures"] += 1
        if child["gate"].get("latency_ms") is not None:
            bucket["gate_latency_ms"].append(child["gate"]["latency_ms"])
        bucket["close_ms"].append(child["close_ms"])

    for bucket in coordinates.values():
        for field in ("gate_latency_ms", "close_ms"):
            values = bucket[field]
            bucket[f"{field}_median"] = round(sorted(values)[len(values) // 2], 3) if values else None
            del bucket[field]

    platform_name = platform.system()
    baseline_failures = sum(
        item["failures"]
        for item in coordinates.values()
        if item["mode"] == "current"
    )
    result = {
        "schema_version": "liminalqa-greg-tee-readiness-platform-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": {
            "system": platform_name,
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "upstream": {
            "repository": "gdb/tee-output",
            "sha": args.upstream_sha,
            "source_path": str(source_path),
            "source_sha256": sha256_file(source_path),
            "static_markers": {
                "openpty": "os.openpty()" in source_text,
                "parent_lifetime_tee": '["parent-lifetime", "--term", "tee", "-a"]' in source_text,
                "sigint_before_wait": "os.kill(proc.pid, signal.SIGINT)" in source_text,
            },
        },
        "matrix": {
            "rounds_per_coordinate": args.rounds,
            "lines_per_fd_stream": args.lines,
            "modes": list(MODES),
            "scenarios": ["issue", "fd"],
            "pty_values": [False, True],
            "total_children": len(entries),
        },
        "coordinates": coordinates,
        "summary": {
            "baseline_failures": baseline_failures,
            "timeouts": timeouts,
            "missing_results": missing_results,
            "execution_complete": timeouts == 0 and missing_results == 0,
        },
        "entries": entries,
    }
    write_json(output_dir / "greg-readiness-platform-result.json", result)

    lines = [
        f"# Greg tee readiness matrix — {platform_name}",
        "",
        f"- children: `{len(entries)}`",
        f"- current-mode failures: `{baseline_failures}`",
        f"- timeouts: `{timeouts}`",
        f"- missing results: `{missing_results}`",
        "",
        "| coordinate | failures | total | gate failures | gate median ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, bucket in sorted(coordinates.items()):
        lines.append(
            f'| `{key}` | {bucket["failures"]} | {bucket["total"]} | '
            f'{bucket["gate_failures"]} | {bucket["gate_latency_ms_median"]} |'
        )
    (output_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if timeouts == 0 and missing_results == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--relay", action="store_true")
    parser.add_argument("--scenario", choices=("issue", "fd"))
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--pty", action="store_true")
    parser.add_argument("--round", type=int)
    parser.add_argument("--round-dir")
    parser.add_argument("--lines", type=int, default=64)
    parser.add_argument("--ready-timeout", type=float, default=5.0)
    parser.add_argument("--ready-file")
    parser.add_argument("relay_command", nargs=argparse.REMAINDER)
    parser.add_argument("--source-file")
    parser.add_argument("--upstream-sha")
    parser.add_argument("--output-dir")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.relay:
        return relay_main(args)
    if args.child:
        return child_main(args)
    return aggregate_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
