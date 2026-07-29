---
name: transition-next-action
description: Convert an audit verdict into the smallest justified next action using checked readiness, causal tension, cooperation, and explicit handoff. Use at the end of an audit or when deciding what to test, fix, escalate, or defer next.
---

# Transition Next Action

## Purpose

An audit is incomplete when it only produces findings. Select the next step without outrunning the evidence or damaging cooperation.

## Readiness handoff

Before proposing action, record:

```text
IFP ready state
-> verified handoff record
-> TIP state
-> validated transition
```

The handoff must bind the exact audit verdict, source identity, unresolved gaps, and authority boundary.

## TIP model

For the current decision, state:

1. **State** — what is known now;
2. **Tension** — what contradiction, risk, or uncertainty creates pressure;
3. **Cause** — why the tension exists, at the supported claim level;
4. **Transition** — the next state that evidence justifies;
5. **Cooperation** — whether users, maintainers, owners, and reviewers retain agency and a clear recovery path;
6. **Action** — the smallest executable next step.

## Action classes

Choose one primary class:

- `COLLECT_EVIDENCE`
- `RUN_DISCRIMINATING_TEST`
- `FIX_CONFIRMED_DEFECT`
- `ADD_GUARDRAIL`
- `MEASURE_IMPACT`
- `HUMAN_ADJUDICATION`
- `DEFER_WITH_WATCHPOINT`
- `STOP_AT_BOUNDARY`

Do not combine several vague actions into “improve everything.”

## Selection rules

Prefer the action that:

- resolves the most load-bearing uncertainty;
- is reversible;
- has a bounded owner and scope;
- preserves evidence;
- does not require authority the auditor lacks;
- creates a clear success/failure signal;
- reduces future audit cost;
- leaves a recovery path.

## Watchpoints

When action is deferred, define:

- the condition that should trigger re-evaluation;
- the evidence source;
- the acceptable checking cadence;
- the expiry or review date;
- the owner;
- the state if the watchpoint cannot run.

A watchpoint that did not run is `NOT_RUN`, not “no change.”

## Output

Return:

- current state;
- load-bearing tension;
- supported cause;
- chosen transition;
- cooperation and recovery check;
- one primary next action;
- owner or required authority;
- exact input/evidence needed;
- completion signal;
- stop condition;
- follow-up transition after success or failure.

## Assurance rule

Every new semantic action rule requires a negative case showing that an invalid transition is rejected. A prose rule without a failing example is advisory guidance, not an enforced contract.
