# Greg tee-output full evidence stack

Date: 2026-07-20

## Purpose

This protocol extends the bounded `gdb/tee-output#3` reproduction from one Linux non-TTY coordinate into a Linux/macOS, PTY/non-PTY and print/fd matrix.

It also maps the resulting evidence into four pinned repositories without overstating what a hosted GitHub runner actually executed.

## Exact inputs

```text
gdb/tee-output
c41f8ff383200320b746e953e92709ae1b505a71

GardenLiminal
6c30422d0492ec312a35624322f90a7761419655

LTP
6284d2fee3f729ceacd688e74c5d67beea1ff3c7

LiminalDB
75ef9f7f403a34c60aa2ceba4cb3c97870d73e77

LiminalOSAI
a2c5783287a9def4b4254b9436c2e75468613dca
```

## Runtime coordinates

The same exact `tee-output` source is executed on:

- GitHub-hosted Ubuntu;
- GitHub-hosted macOS;
- PTY and non-PTY child processes;
- the original issue-shaped `print → traceback → immediate close` path;
- direct `os.write` records, which isolate shutdown from Python buffering;
- delays of 0, 1, 10 and 100 ms;
- current upstream shutdown and a one-variable safe-shutdown counterfactual.

Each coordinate is repeated six times.

## Counterfactual

The patched observer changes only shutdown order:

```text
flush Python wrappers
→ restore stdout/stderr descriptors
→ close all pipe writers and deliver EOF
→ wait for tee readers naturally
→ terminate and then kill only after bounded timeouts
```

No patch is committed to the upstream repository.

## GardenLiminal layer

Integration mode:

```text
CONTRACT_ADAPTER_NO_PRIVILEGED_RUNTIME
```

The packet contains a Garden-style Seed and lifecycle events. The contract validator requires every child trajectory to include creation, loading, process start, close request, close completion, evidence observation and process exit.

Hosted runners are not claimed to have executed Garden namespaces, cgroups, capability dropping or seccomp. The exact Garden commit is checked out and its Cargo manifest is validated separately.

## LTP layer

Integration mode:

```text
CONTRACT_ADAPTER_WITH_DETERMINISTIC_REPLAY
```

Each child path becomes an ordered trace with parent-linked events and a terminal verification. Replay classifies the path as:

- `admissible` — the trajectory is complete and output verification passed;
- `rejected` — the trajectory is complete but expected evidence is missing;
- `drift` — the trajectory is incomplete or non-monotonic.

The exact LTP repository runs its own `pnpm test` suite. This does not claim that a hosted LTP service processed the evidence packet.

## LiminalDB layer

Integration mode:

```text
FILE_BACKED_EVENT_SOURCED_ADAPTER_NO_LIVE_DAEMON
```

All events are transformed into append-only impulses. Every record contains a sequence number, the previous record hash and its own SHA-256 hash. Independent replay verifies sequence and chain integrity.

The exact LiminalDB Cargo workspace metadata is validated. No claim is made that a live daemon persisted the records.

## LiminalOSAI layer

Integration mode:

```text
ADVISORY_ONLY_RULE_BASED_OBSERVER
```

The exact LiminalOSAI revision is built and its `make check` and `make test` paths run. Its contribution to the Greg packet is limited to rule-based advisory observations such as platform divergence, bounded non-reproduction and remaining static shutdown-order risk.

LiminalOSAI cannot confirm a bug, authorize notification or change external state.

## Verdicts

```text
baseline loss + clean counterfactual
→ READY_TO_NOTIFY_DATA_LOSS_WITH_COUNTERFACTUAL_SUPPORT

no baseline loss on Linux or macOS
→ READY_TO_NOTIFY_CROSS_PLATFORM_NON_REPRODUCTION_STATIC_RISK_REMAINS

baseline and counterfactual both fail
→ HOLD_COUNTERFACTUAL_INCONCLUSIVE

missing platform, timeout, broken replay or stale component contract
→ BLOCKED_DO_NOT_NOTIFY
```

Non-reproduction is not disproof. A message must name the tested coordinates and preserve the original reporter's untested environment details.

## Authority boundary

The stack may produce an evidence comment only after the final gate passes. It may not:

- approve a pull request;
- close an issue or pull request;
- assign or label third-party work;
- merge code;
- modify the upstream package;
- claim production impact;
- convert an advisory observation into a confirmed cause.
