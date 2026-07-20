#!/usr/bin/env python3
# Apply the bounded READY-handshake + EOF-drain candidate for gdb/tee-output#3.
# Every source replacement must match once against the pinned upstream revision.

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one source match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


RELAY_FILE = r'''"""Small binary relay used by :mod:`tee_output`.

The relay opens every output target before acknowledging readiness, then copies
stdin to the original stream and all targets until EOF. Exiting only after the
read loop finishes gives ``Tee.close()`` a concrete drain-completion boundary.
"""

import argparse
import errno
import os


def copy_stream(paths, ready_fd):
    outputs = [open(path, "ab", buffering=0) for path in paths]
    try:
        os.write(ready_fd, b"1")
    finally:
        os.close(ready_fd)

    try:
        while True:
            try:
                chunk = os.read(0, 65536)
            except OSError as exc:
                # Closing a PTY master is reported as EIO on some platforms.
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break

            os.write(1, chunk)
            for output in outputs:
                output.write(chunk)
    finally:
        for output in outputs:
            output.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready-fd", type=int, required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    copy_stream(args.paths, args.ready_fd)


if __name__ == "__main__":
    main()
'''


TEST_FILE = r'''import errno
import os
import pty
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


CHILD = textwrap.dedent(
    r"""
    import sys
    import traceback
    from pathlib import Path
    from tee_output import Tee

    root = Path(sys.argv[1])
    stdout = [str(root / "stdout.log"), str(root / "combined.log")]
    stderr = [str(root / "stderr.log"), str(root / "combined.log")]

    tee = Tee().to(stdout=stdout, stderr=stderr)
    print("stdout-marker", flush=True)
    try:
        raise RuntimeError("stderr-marker")
    except RuntimeError:
        traceback.print_exc()
    finally:
        tee.close()
    """
)


def read_terminal(master):
    chunks = []
    while True:
        try:
            chunk = os.read(master, 65536)
        except OSError as exc:
            if exc.errno == errno.EIO:
                break
            raise
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


class ImmediateCloseTest(unittest.TestCase):
    def test_print_traceback_immediate_close_preserves_all_outputs(self):
        for round_id in range(10):
            with self.subTest(round=round_id), tempfile.TemporaryDirectory() as tmp:
                master, slave = pty.openpty()
                try:
                    proc = subprocess.Popen(
                        [sys.executable, "-u", "-c", CHILD, tmp],
                        stdin=slave,
                        stdout=slave,
                        stderr=slave,
                        close_fds=True,
                    )
                finally:
                    os.close(slave)

                terminal = read_terminal(master)
                os.close(master)
                self.assertEqual(
                    proc.wait(timeout=10),
                    0,
                    terminal.decode(errors="replace"),
                )

                root = Path(tmp)
                stdout_text = (root / "stdout.log").read_text()
                stderr_text = (root / "stderr.log").read_text()
                combined = (root / "combined.log").read_text()
                terminal_text = terminal.decode(errors="replace")

                self.assertIn("stdout-marker", stdout_text)
                self.assertIn("stderr-marker", stderr_text)
                self.assertIn("stdout-marker", combined)
                self.assertIn("stderr-marker", combined)
                self.assertIn("stdout-marker", terminal_text)
                self.assertIn("stderr-marker", terminal_text)


if __name__ == "__main__":
    unittest.main()
'''


WORKFLOW_FILE = r'''name: test

on:
  pull_request:
  push:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os:
          - ubuntu-latest
          - macos-latest
        python:
          - "3.11"
          - "3.13"
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e .
      - run: python -m unittest discover -s tests -v
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--patch-out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()

    tee = repo / "tee_output/__init__.py"
    parent = repo / "bin/parent-lifetime"
    relay = repo / "tee_output/_relay.py"

    replace_once(
        tee,
        "import os\nimport signal\n",
        "import os\nimport select\nimport signal\n",
    )

    replace_once(
        tee,
        '''    def close(self):
        self.pause()
        self._drain(self.stdout_pipe_proc, self.stderr_pipe_proc)

    def _drain(self, stdout_pipe_proc, stderr_pipe_proc):
        # One sharp edge is that if you've spawned a subprocess with
        # the redirected stdout/stderr, the tee processes will not
        # die. In that case maybe we should set a timeout, or just
        # leak them? Not sure.
        if stdout_pipe_proc is not None:
            pipe, proc = stdout_pipe_proc
            pipe.close()
            try:
                # TODO: replace tee with something that is guaranteed
                # to flush on exit
                os.kill(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            proc.wait()
        if stderr_pipe_proc is not None:
            pipe, proc = stderr_pipe_proc
            pipe.close()
            try:
                os.kill(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            proc.wait()
''',
        '''    def close(self):
        # Flush Python-level buffers before restoring the original descriptors.
        sys.stdout.flush()
        sys.stderr.flush()
        self.pause()
        self._drain(self.stdout_pipe_proc, self.stderr_pipe_proc)

    def _drain(self, stdout_pipe_proc, stderr_pipe_proc):
        # Closing the writer delivers EOF to the bundled relay. Natural process
        # completion is the drain acknowledgement; SIGINT is only a bounded
        # fallback for inherited descriptors or a stuck reader.
        self._drain_one(stdout_pipe_proc)
        self._drain_one(stderr_pipe_proc)

    @staticmethod
    def _drain_one(pipe_proc):
        if pipe_proc is None:
            return

        pipe, proc = pipe_proc
        pipe.close()
        try:
            proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass

        try:
            os.kill(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            return
        proc.wait()
''',
    )

    replace_once(
        tee,
        '''    # TODO: fast exit
    proc = subprocess.Popen(
        ["parent-lifetime", "--term", "tee", "-a"] + list(to),
        stdin=r,
        start_new_session=True,
        stderr=subprocess.DEVNULL,
        stdout=stdout,
        preexec_fn=set_ctty,
    )
    r.close()
    return w, proc
''',
        '''    # The relay acknowledges only after every target has been opened. This
    # distinguishes "process spawned" from "reader ready" and prevents the
    # first write from racing external tee startup.
    ready_r, ready_w = os.pipe()
    proc = subprocess.Popen(
        [
            "parent-lifetime",
            "--term",
            sys.executable,
            "-m",
            "tee_output._relay",
            "--ready-fd",
            str(ready_w),
        ]
        + list(to),
        stdin=r,
        start_new_session=True,
        stderr=subprocess.DEVNULL,
        stdout=stdout,
        preexec_fn=set_ctty,
        pass_fds=(ready_w,),
    )
    r.close()
    os.close(ready_w)

    ready, _, _ = select.select([ready_r], [], [], 2)
    marker = os.read(ready_r, 1) if ready else b""
    os.close(ready_r)
    if marker != b"1":
        w.close()
        try:
            os.kill(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        proc.wait()
        raise RuntimeError("tee relay did not become ready")

    return w, proc
''',
    )

    replace_once(
        parent,
        '''    # Let the process die naturally
    while True:
        if child.poll() is not None:
            return child.returncode
        elif os.getppid() == 1:
            break
        time.sleep(poll_timeout)
''',
        '''    # Let the process die naturally. Waiting on the child directly observes
    # EOF-driven completion immediately; the timeout only provides a cadence
    # for checking whether our own parent disappeared.
    while True:
        try:
            child.wait(timeout=poll_timeout)
            return child.returncode
        except subprocess.TimeoutExpired:
            if os.getppid() == 1:
                break
''',
    )

    relay.write_text(RELAY_FILE, encoding="utf-8")

    tests = repo / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_immediate_close.py").write_text(TEST_FILE, encoding="utf-8")

    workflow = repo / ".github/workflows"
    workflow.mkdir(parents=True, exist_ok=True)
    (workflow / "test.yml").write_text(WORKFLOW_FILE, encoding="utf-8")

    subprocess.run(
        [
            "python",
            "-m",
            "py_compile",
            str(tee),
            str(parent),
            str(relay),
            str(tests / "test_immediate_close.py"),
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "diff", "--check"], check=True)
    args.patch_out.parent.mkdir(parents=True, exist_ok=True)
    patch = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary"])
    args.patch_out.write_bytes(patch)


if __name__ == "__main__":
    main()
