# Finding Template

Use one file per finding. Keep claims limited to demonstrated behavior in the authorized environment.

## Finding ID

`F-XXX`

## Title

Short, factual, outcome-oriented title.

## Status

- `OPEN`
- `FIX_READY`
- `RETEST_PASS`
- `RETEST_FAIL`
- `ACCEPTED_RISK`
- `INCONCLUSIVE`

## Severity

- Critical / High / Medium / Low / Observation

## Delivery priority

- P0 / P1 / P2 / P3

## Summary

One paragraph describing:

- what action was performed;
- what was observed;
- what business rule was violated;
- why the result matters.

## Preconditions

- Environment:
- Build / version:
- Test identity / account:
- Seed state:
- Relevant limits / configuration:

## Reproduction path

1.
2.
3.
4.

## Expected result

State the agreed business rule or acceptance criterion.

## Observed result

State only what was actually observed.

## Evidence

| Evidence ID | Description | Location / reference |
|---|---|---|
| E-001 |  |  |
| E-002 |  |  |

Never include secrets, raw production credentials, or unnecessary personal data.

## State transition

```text
PRE-STATE
   ↓
ACTION
   ↓
OBSERVED RESPONSE / EVENT
   ↓
POST-STATE
```

Pre-state:

Post-state:

## Business impact

Describe the demonstrated impact, for example:

- duplicate logical action;
- business limit exceeded;
- incorrect accounting state;
- lost or stuck workflow state;
- rejected action still changed counters;
- audit record does not match business state;
- user cannot complete a valid workflow.

Do not extrapolate beyond the evidence.

## Frequency / trigger

- Deterministic / intermittent / not established
- Trigger conditions:

## Suggested acceptance criterion

A testable statement, e.g.:

> When two authorized test requests race against the same remaining quota, the final committed total must not exceed the configured limit, and every rejected request must leave spend counters unchanged.

## Suggested remediation direction

Describe the behavior to preserve or the invariant to enforce. Avoid prescribing an implementation unless the client asks for one and evidence supports it.

## Retest

- Fix/build tested:
- Date:
- Same reproduction path used: yes / no
- Result: PASS / FAIL / BLOCKED / INCONCLUSIVE
- Evidence:

## Notes

Any ambiguity, limitation, or follow-up question.
