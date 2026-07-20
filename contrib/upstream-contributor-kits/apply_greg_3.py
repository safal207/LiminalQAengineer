#!/usr/bin/env python3
# Apply the bounded candidate fix for gdb/tee-output#3.
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
                self.assertIn("stdout-marker", (root / "stdout.log").read_text())
                self.assertIn("stderr-marker", (root / "stderr.log").read_text())
                combined = (root / "combined.log").read_text()
                self.assertIn("stdout-marker", combined)
                self.assertIn("stderr-marker", combined)


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
        # This is separate from draining the external tee processes below.
        sys.stdout.flush()
        sys.stderr.flush()
        self.pause()
        self._drain(self.stdout_pipe_proc, self.stderr_pipe_proc)

    def _drain(self, stdout_pipe_proc, stderr_pipe_proc):
        # One sharp edge is that if you've spawned a subprocess with
        # the redirected stdout/stderr, the tee processes will not die from EOF.
        # Preserve bounded shutdown for that case, but do not interrupt the
        # normal path before tee has had a chance to drain.
        self._drain_one(stdout_pipe_proc)
        self._drain_one(stderr_pipe_proc)

    @staticmethod
    def _drain_one(pipe_proc):
        if pipe_proc is None:
            return

        pipe, proc = pipe_proc
        pipe.close()

        try:
            # Closing the final writer delivers EOF. Let tee consume the
            # buffered PTY/pipe tail and exit naturally before using signals.
            proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass

        try:
            # Fallback for inherited descriptors or a stuck reader stack.
            os.kill(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            return
        proc.wait()
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
