# Greg `tee-output#3` — readiness-handshake protocol

## Purpose

The prior cross-platform matrix confirmed a timing-sensitive PTY output-loss
symptom, but the shutdown-order counterfactual did not isolate a sole cause.
This stacked experiment tests the narrower candidate:

> writes may occur before the external `parent-lifetime -> tee` reader path has
> reached a usable startup state.

The experiment does **not** assume that candidate is true.

## Observer coordinates

The observer is read-only and fixed to:

```text
upstream: gdb/tee-output
source SHA: c41f8ff383200320b746e953e92709ae1b505a71
platforms: GitHub-hosted Ubuntu and macOS
Python: 3.11
output coordinate: PTY and non-PTY
payload coordinate: issue-shaped print/traceback and direct os.write
```

## Modes

| Mode | Write permission |
|---|---|
| `current` | immediately after `Tee.to()` |
| `sleep100` | after a fixed 100 ms delay |
| `file_exists` | after stdout, stderr, and combined files exist |
| `supervisor_ack` | after the real system `tee` is alive and all targets exist |
| `supervisor_ack_safe_close` | same acknowledgement plus the shutdown-order counterfactual |

`supervisor_ack` preserves the real system `tee` and `parent-lifetime`. A small
wrapper launches `tee`, observes child liveness and target creation, and emits a
machine-readable acknowledgement.

## LPI adaptation

```text
Hello   = parent-lifetime process requested
Mirror  = command and target paths observed
Bind    = real tee child spawned
Seal    = tee child alive + all target files exist
Flow    = CaPU write gate opened
```

This is a process-startup adaptation of LPI/LHS. It is not a claim of network
protocol conformance.

## CaPU adaptation

```text
Gate      = mode and preconditions validated
Incubate  = wait for delay, file existence, or acknowledgement
Commit    = write permission recorded
Execute   = print/os.write payload emitted
Effect    = output files verified
```

No payload is written when the selected gate fails.

## Evidence layers

- **T-Trace:** acknowledged `sense -> transition -> commit` records.
- **TTM DB adapter:** append-only raw event chain with replay verification.
- **SDP:** decomposition from the broad race claim into pico hypotheses.
- **DRP:** preserves the previous shutdown conclusion and records the new
  readiness decision through explicit supersession.
- **CML/Pythia/ProofPath boundary:** a symptom or candidate may be reported, but
  an unresolved candidate may not be promoted to a sole root cause.

## Causal interpretations

```text
current fails + file_exists passes
=> pre-output-open startup window is supported

file_exists fails + supervisor_ack passes
=> child-liveness acknowledgement adds evidence beyond path existence

supervisor_ack fails
=> readiness barrier is not sufficient

supervisor_ack passes + safe_close improves further
=> startup and shutdown may both contribute
```

## Non-claims

The supervisory acknowledgement does not prove that the system `tee` reached a
particular source-code instruction or blocking read call. The wrapper also adds
one supervisory process to the process tree. Both facts must be disclosed in
any external comment.

This workflow makes no changes to the upstream repository, issue state, labels,
reviews, approvals, closes, or merges.
