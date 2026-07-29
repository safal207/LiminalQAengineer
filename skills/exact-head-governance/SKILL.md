---
name: exact-head-governance
description: Bind repository and pull-request audit conclusions to one exact commit, frozen evidence, real execution states, and human adjudication. Use whenever code, a branch, CI result, or pull request is part of an audit.
---

# Exact-Head Governance

## Objective

Prevent a correct-looking report from describing code that has already changed.

This skill has evidence and advisory authority only. It cannot approve, merge, push, deploy, dismiss review concerns, or impersonate a repository owner.

## Required identity

Record:

- repository full name;
- PR number or branch;
- base SHA;
- expected 40-character head SHA;
- workflow SHA and run attempt;
- collection start and end timestamps.

Do not accept a branch name alone as evidence identity.

## Collection sequence

```text
PR URL + expected head SHA
-> initial head check
-> frozen evidence collection
-> final head check
-> PASS | HOLD | NOT_RUN | INCOMPLETE
-> human adjudication
```

## Fail-closed rules

- Initial head mismatch: `HOLD`.
- Final head mismatch: `HOLD`.
- Force-push during collection: cannot produce `PASS`.
- A job that did not run is `NOT_RUN`, not green.
- A missing credential or unavailable reviewer is `INCOMPLETE`, not approval.
- Commentary-only or stale review evidence is incomplete.
- `CHANGES_REQUESTED` remains `HOLD` until the exact-head concern is resolved or explicitly adjudicated by an authorized human.
- Human adjudication cannot waive exact-head identity.
- The audit cannot approve or merge a pull request.

## Evidence bundle

Produce or reference:

```text
manifest.json
scorecard.json
SCORECARD.md
adjudication-template.json
evidence/
ARTIFACT_SHA256SUMS.txt
```

The human-readable scorecard summarizes the evidence. It must not replace the raw bundle.

## Check semantics

For every check, record one of:

- `PASS`
- `FAIL`
- `NOT_RUN`
- `UNAVAILABLE`
- `STALE`
- `INCOMPLETE`

Never collapse the last four into `PASS` or omit them from the denominator.

## Review semantics

Distinguish:

- approval anchored to the exact head;
- changes requested anchored to the exact head;
- general discussion;
- bot commentary;
- stale review anchored to an earlier head;
- unavailable reviewer state.

Automated review is evidence, not human approval, unless a repository policy explicitly defines otherwise.

## Output

Return:

- exact identity verdict;
- collection completeness;
- blocking review state;
- check matrix;
- stale or missing evidence;
- artifact integrity status;
- advisory risk scorecard;
- authority boundary;
- human decisions still required.

The final status must preserve the worst load-bearing state. A mostly green matrix with one unknown required check is not fully green.
