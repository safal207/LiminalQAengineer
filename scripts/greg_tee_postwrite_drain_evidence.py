#!/usr/bin/env python3
"""Post-write drain counterfactual for gdb/tee-output#3.

This experiment starts from the supervisory startup acknowledgement introduced
in the readiness pass, writes a bounded payload, and varies only the transition
between the completed user write call and ``Tee.close()``.

The key distinction is:

    startup acknowledgement != payload drain acknowledgement

The output-complete barrier is observational. It proves that all expected
records reached the configured output files before close; it does not claim an
internal source-level acknowledgement from the system ``tee`` process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import select
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

import greg_tee_readiness_handshake_evidence as readiness

MODES = (
    "ack_immediate",
    "ack_postwrite_1ms",
    "ack_postwrite_5ms",
    "ack_postwrite_10ms",
    "ack_postwrite_25ms",
    "ack_quiescence_5ms",
    "ack_output_complete",
    "ack_output_complete_safe_close",
    "direct_ack_safe_close",
    "direct_ack_output_complete_safe_close",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_json(path: Path, value: Any) -> None:
    readiness.write_json(path, value)


def event(events: list[dict[str, Any]], name: str, **details: Any) -> None:
    readiness.event(events, name, **details)


def install_direct_supervisor_wrapper(
    *, script: Path, round_dir: Path
) -> tuple[list[Path], Callable[[], None]]:
    """Replace parent-lifetime with the same relay directly, retaining real tee."""

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
            ready_path = round_dir / f"direct-supervisor-ready-{counter}.json"
            ready_files.append(ready_path)
            rewritten = [
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


def expected_complete(
    *,
    stdout_text: str,
    stderr_text: str,
    combined_text: str,
    expected_stdout: list[str],
    expected_stderr: list[str],
    expected_stderr_substrings: list[str],
) -> bool:
    return (
        all(value in stdout_text for value in expected_stdout)
        and all(value in stderr_text for value in expected_stderr)
        and all(value in stderr_text for value in expected_stderr_substrings)
        and all(
            value in combined_text
            for value in [*expected_stdout, *expected_stderr, *expected_stderr_substrings]
        )
    )


def wait_output_complete(
    *,
    stdout_path: Path,
    stderr_path: Path,
    combined_path: Path,
    expected_stdout: list[str],
    expected_stderr: list[str],
    expected_stderr_substrings: list[str],
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic_ns()
    deadline = time.monotonic() + timeout
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        stdout_text = read_text(stdout_path)
        stderr_text = read_text(stderr_path)
        combined_text = read_text(combined_path)
        if expected_complete(
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            combined_text=combined_text,
            expected_stdout=expected_stdout,
            expected_stderr=expected_stderr,
            expected_stderr_substrings=expected_stderr_substrings,
        ):
            return {
                "passed": True,
                "kind": "observed_output_complete",
                "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
                "polls": polls,
                "sizes": {
                    "stdout": len(stdout_text.encode()),
                    "stderr": len(stderr_text.encode()),
                    "combined": len(combined_text.encode()),
                },
            }
        time.sleep(0.0005)
    return {
        "passed": False,
        "kind": "observed_output_complete",
        "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
        "polls": polls,
        "missing": {
            "stdout": [value for value in expected_stdout if value not in read_text(stdout_path)][:20],
            "stderr": [value for value in expected_stderr if value not in read_text(stderr_path)][:20],
            "stderr_substrings": [
                value for value in expected_stderr_substrings if value not in read_text(stderr_path)
            ],
        },
    }


def wait_quiescence(
    *, paths: list[Path], timeout: float, stable_ms: float = 5.0
) -> dict[str, Any]:
    started = time.monotonic_ns()
    deadline = time.monotonic() + timeout
    previous: tuple[int, ...] | None = None
    stable_since: int | None = None
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        sizes = tuple(path.stat().st_size if path.exists() else -1 for path in paths)
        now = time.monotonic_ns()
        if all(value > 0 for value in sizes):
            if sizes == previous:
                stable_since = stable_since or now
                if (now - stable_since) / 1_000_000 >= stable_ms:
                    return {
                        "passed": True,
                        "kind": "positive_size_quiescence",
                        "latency_ms": round((now - started) / 1_000_000, 3),
                        "stable_ms": round((now - stable_since) / 1_000_000, 3),
                        "polls": polls,
                        "sizes": list(sizes),
                    }
            else:
                stable_since = now
        else:
            stable_since = None
        previous = sizes
        time.sleep(0.0005)
    return {
        "passed": False,
        "kind": "positive_size_quiescence",
        "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
        "polls": polls,
        "sizes": list(previous or ()),
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
    trace_id = f"greg-drain-{uuid.uuid4()}"
    coordinate = {
        "scenario": args.scenario,
        "pty": True,
        "mode": args.mode,
        "round": args.round,
    }
    event(events, "SENSE_DRAIN_RUN_CREATED", trace_id=trace_id, coordinate=coordinate)
    before_isatty = {"stdout": sys.stdout.isatty(), "stderr": sys.stderr.isatty()}
    event(events, "SENSE_OBSERVER_BOUND", isatty=before_isatty)

    direct = args.mode.startswith("direct_")
    if direct:
        ready_files, restore_wrapper = install_direct_supervisor_wrapper(
            script=script, round_dir=round_dir
        )
        process_topology = "relay_to_tee_without_parent_lifetime"
    else:
        ready_files, restore_wrapper = readiness.install_supervisor_wrapper(
            script=script, round_dir=round_dir
        )
        process_topology = "parent_lifetime_to_relay_to_tee"
    event(events, "TRANSITION_STARTUP_SUPERVISOR_INSTALLED", topology=process_topology)

    safe_close = args.mode.endswith("safe_close")
    if safe_close:
        readiness.install_safe_shutdown_counterfactual()
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

    startup_gate = readiness.wait_for_acknowledgements(
        ready_files, timeout=args.ready_timeout
    )
    startup_gate.update({"mode": args.mode, "topology": process_topology})
    event(events, "TRANSITION_STARTUP_ACK_RECEIVED", gate=startup_gate)
    if startup_gate.get("passed"):
        event(events, "COMMIT_WRITE_GATE_OPENED")
    else:
        event(events, "COMMIT_WRITE_GATE_REJECTED")

    expected_stdout: list[str] = []
    expected_stderr: list[str] = []
    expected_stderr_substrings: list[str] = []
    if startup_gate.get("passed"):
        if args.scenario == "issue":
            stdout_marker = f"ISSUE-STDOUT:{args.round:04d}"
            stderr_marker = f"ISSUE-STDERR:{args.round:04d}"
            assertion_marker = f"liminalqa-drain-{args.round:04d}"
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
            event(events, "TRANSITION_ISSUE_PAYLOAD_DISPATCHED")
        else:
            expected_stdout = [f"STDOUT:{index:06d}" for index in range(args.lines)]
            expected_stderr = [f"STDERR:{index:06d}" for index in range(args.lines)]
            for stdout_record, stderr_record in zip(
                expected_stdout, expected_stderr, strict=True
            ):
                os.write(sys.stdout.fileno(), f"{stdout_record}\n".encode())
                os.write(sys.stderr.fileno(), f"{stderr_record}\n".encode())
            event(events, "TRANSITION_FD_BURST_DISPATCHED", lines_per_stream=args.lines)

    postwrite: dict[str, Any] = {"kind": "none", "passed": True, "latency_ms": 0.0}
    delay_map = {
        "ack_postwrite_1ms": 0.001,
        "ack_postwrite_5ms": 0.005,
        "ack_postwrite_10ms": 0.010,
        "ack_postwrite_25ms": 0.025,
    }
    if args.mode in delay_map:
        started = time.monotonic_ns()
        time.sleep(delay_map[args.mode])
        postwrite = {
            "kind": "fixed_postwrite_delay",
            "passed": True,
            "requested_ms": delay_map[args.mode] * 1000,
            "latency_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
        }
    elif args.mode == "ack_quiescence_5ms":
        postwrite = wait_quiescence(
            paths=[stdout_path, stderr_path, combined_path],
            timeout=args.drain_timeout,
            stable_ms=5.0,
        )
    elif "output_complete" in args.mode:
        postwrite = wait_output_complete(
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            combined_path=combined_path,
            expected_stdout=expected_stdout,
            expected_stderr=expected_stderr,
            expected_stderr_substrings=expected_stderr_substrings,
            timeout=args.drain_timeout,
        )
    event(events, "TRANSITION_POSTWRITE_BARRIER_RESOLVED", barrier=postwrite)
    if postwrite.get("passed"):
        event(events, "COMMIT_CLOSE_GATE_OPENED")
    else:
        event(events, "COMMIT_CLOSE_GATE_REJECTED")

    event(events, "TRANSITION_CLOSE_REQUESTED")
    close_started = time.monotonic()
    tee.close()
    close_ms = round((time.monotonic() - close_started) * 1000, 3)
    event(events, "TRANSITION_CLOSE_COMPLETED", close_ms=close_ms)
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
    passed = (
        bool(startup_gate.get("passed"))
        and bool(postwrite.get("passed"))
        and not missing_stdout
        and not missing_stderr
        and not missing_stderr_substrings
        and not missing_combined
    )
    event(events, "COMMIT_OUTPUT_VERIFIED", passed=passed)

    result = {
        "schema_version": "liminalqa-greg-tee-postwrite-child-v1",
        "trace_id": trace_id,
        "coordinate": coordinate,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
            "isatty_before_redirect": before_isatty,
        },
        "process_topology": process_topology,
        "startup_gate": startup_gate,
        "postwrite_barrier": postwrite,
        "close_ms": close_ms,
        "verification": {
            "passed": passed,
            "missing_stdout": missing_stdout[:20],
            "missing_stderr": missing_stderr[:20],
            "missing_stderr_substrings": missing_stderr_substrings,
            "missing_combined": missing_combined[:20],
        },
        "files": {
            "stdout": {
                "exists": stdout_path.exists(),
                "bytes": len(stdout_text.encode()),
                "sha256": sha256_file(stdout_path),
            },
            "stderr": {
                "exists": stderr_path.exists(),
                "bytes": len(stderr_text.encode()),
                "sha256": sha256_file(stderr_path),
            },
            "combined": {
                "exists": combined_path.exists(),
                "bytes": len(combined_text.encode()),
                "sha256": sha256_file(combined_path),
            },
        },
        "counterfactual_waits": getattr(tee, "_liminalqa_waits", None),
        "events": events,
    }
    write_json(result_path, result)
    return 0


def run_child(
    *,
    script: Path,
    scenario: str,
    mode: str,
    round_number: int,
    lines: int,
    output_dir: Path,
    timeout: float,
    ready_timeout: float,
    drain_timeout: float,
) -> dict[str, Any]:
    coordinate_name = f"{scenario}-pty-1-{mode}"
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
        "--drain-timeout",
        str(drain_timeout),
    ]
    process = readiness.run_with_pty(command, timeout)
    result_path = round_dir / "child-result.json"
    child_result = json.loads(result_path.read_text()) if result_path.exists() else None
    return {"process": process, "result": child_result}


def aggregate_main(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    entries: list[dict[str, Any]] = []
    for scenario in ("issue", "fd"):
        for mode in MODES:
            for round_number in range(1, args.rounds + 1):
                entries.append(
                    run_child(
                        script=script,
                        scenario=scenario,
                        mode=mode,
                        round_number=round_number,
                        lines=args.lines,
                        output_dir=output_dir,
                        timeout=args.timeout,
                        ready_timeout=args.ready_timeout,
                        drain_timeout=args.drain_timeout,
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
        key = f'{coordinate["scenario"]}|{coordinate["mode"]}'
        bucket = coordinates.setdefault(
            key,
            {
                "scenario": coordinate["scenario"],
                "mode": coordinate["mode"],
                "total": 0,
                "failures": 0,
                "startup_gate_failures": 0,
                "postwrite_barrier_failures": 0,
                "startup_latency_ms": [],
                "postwrite_latency_ms": [],
                "close_ms": [],
            },
        )
        bucket["total"] += 1
        if not child["verification"]["passed"]:
            bucket["failures"] += 1
        if not child["startup_gate"].get("passed", False):
            bucket["startup_gate_failures"] += 1
        if not child["postwrite_barrier"].get("passed", False):
            bucket["postwrite_barrier_failures"] += 1
        if child["startup_gate"].get("latency_ms") is not None:
            bucket["startup_latency_ms"].append(child["startup_gate"]["latency_ms"])
        if child["postwrite_barrier"].get("latency_ms") is not None:
            bucket["postwrite_latency_ms"].append(child["postwrite_barrier"]["latency_ms"])
        bucket["close_ms"].append(child["close_ms"])

    for bucket in coordinates.values():
        for field in ("startup_latency_ms", "postwrite_latency_ms", "close_ms"):
            values = bucket[field]
            bucket[f"{field}_median"] = (
                round(sorted(values)[len(values) // 2], 3) if values else None
            )
            del bucket[field]

    result = {
        "schema_version": "liminalqa-greg-tee-postwrite-platform-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "upstream": {
            "repository": "gdb/tee-output",
            "sha": args.upstream_sha,
        },
        "matrix": {
            "modes": list(MODES),
            "scenarios": ["issue", "fd"],
            "rounds_per_coordinate": args.rounds,
            "lines_per_fd_stream": args.lines,
            "total_children": len(entries),
            "pty": True,
        },
        "coordinates": coordinates,
        "summary": {
            "timeouts": timeouts,
            "missing_results": missing_results,
            "execution_complete": timeouts == 0 and missing_results == 0,
        },
        "entries": entries,
    }
    write_json(output_dir / "greg-postwrite-platform-result.json", result)

    lines = [
        f"# Greg tee post-write matrix — {platform.system()}",
        "",
        f"- children: `{len(entries)}`",
        f"- timeouts: `{timeouts}`",
        f"- missing results: `{missing_results}`",
        "",
        "| coordinate | failures | total | startup gate failures | postwrite barrier failures | postwrite median ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, bucket in sorted(coordinates.items()):
        lines.append(
            f'| `{key}` | {bucket["failures"]} | {bucket["total"]} | '
            f'{bucket["startup_gate_failures"]} | {bucket["postwrite_barrier_failures"]} | '
            f'{bucket["postwrite_latency_ms_median"]} |'
        )
    (output_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if timeouts == 0 and missing_results == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--relay", action="store_true")
    parser.add_argument("--scenario", choices=("issue", "fd"))
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--round", type=int)
    parser.add_argument("--round-dir")
    parser.add_argument("--lines", type=int, default=64)
    parser.add_argument("--ready-timeout", type=float, default=5.0)
    parser.add_argument("--drain-timeout", type=float, default=5.0)
    parser.add_argument("--ready-file")
    parser.add_argument("relay_command", nargs=argparse.REMAINDER)
    parser.add_argument("--upstream-sha")
    parser.add_argument("--output-dir")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=25.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.relay:
        return readiness.relay_main(args)
    if args.child:
        return child_main(args)
    return aggregate_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
