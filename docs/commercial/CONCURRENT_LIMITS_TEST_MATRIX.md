# Concurrent Limits Test Matrix

Generic template for authorized test/staging validation of business limits under simultaneous or retried requests.

This is a reliability QA matrix, not a production load test or offensive security playbook.

## Preconditions

Freeze before execution:

- test environment;
- test identity/account/wallet;
- starting counters/balance/state;
- per-action limit;
- daily limit;
- monthly or rolling limit;
- idempotency mechanism;
- retry policy;
- approved concurrency level;
- approved request-rate ceiling;
- expected response/status semantics.

## Outcome vocabulary

- `PASS` — observed result matches the agreed rule;
- `FAIL` — reproducible deviation;
- `BLOCKED` — execution unavailable;
- `INCONCLUSIVE` — evidence insufficient.

## Matrix

| ID | Scenario | Pre-state | Actions | Expected invariant | Evidence |
|---|---|---|---|---|---|
| CL-001 | below per-action limit | clean state | one request below threshold | accepted once; counters change once | request/response + state |
| CL-002 | exactly at per-action limit | clean state | one request at threshold | follows documented boundary rule | request/response + state |
| CL-003 | above per-action limit | clean state | one request above threshold | rejected; counters/state unchanged except allowed audit metadata | request/response + state |
| CL-004 | two requests individually valid, jointly exceed remaining daily limit | near daily limit | two simultaneous requests | committed total never exceeds daily limit | timestamps + responses + final counters |
| CL-005 | two requests individually valid, jointly exceed remaining monthly/rolling limit | near monthly limit | two simultaneous requests | committed total never exceeds monthly/rolling limit | timestamps + final counters |
| CL-006 | per-action allows but daily denies | daily limit nearly exhausted | one request | daily rule wins consistently; no partial accounting | response + state |
| CL-007 | daily allows but monthly denies | monthly limit nearly exhausted | one request | monthly rule wins consistently; no partial accounting | response + state |
| CL-008 | duplicate request identifier | clean state | same logical request twice | at most one logical effect | responses + business state |
| CL-009 | retry after client-visible timeout | clean state | request, timeout condition, authorized retry | one logical effect or documented recoverable state | request IDs + final state |
| CL-010 | rejected request followed by valid request | near limit | invalid/over-limit then valid | rejected action does not consume allowance unless explicitly documented | counters before/after |
| CL-011 | small approved burst against same resource | known remaining allowance | N simultaneous requests within approved ceiling | accepted total respects all limits; final state explainable | batch result + final state |
| CL-012 | mixed duplicate + concurrent requests | clean state | duplicate logical actions submitted concurrently | no duplicate logical effect | IDs + final state |
| CL-013 | one accepted, one conflicting action | near limit | simultaneous conflicting requests | final outcome respects invariant and exposes clear status for each request | responses + final state |
| CL-014 | post-failure recovery | known state | induce only an approved non-destructive dependency failure, then retry | no double effect; state converges to documented outcome | logs/state/retry result |
| CL-015 | audit consistency | any above scenario | compare business result and audit record | audit trail reflects the committed business outcome | sanitized audit evidence |

## Recommended boundary values

For a configured limit `L`, use only non-destructive test values approved by the client:

- clearly below `L`;
- exactly `L` where supported;
- minimally above `L`;
- remaining allowance minus a small unit;
- remaining allowance exactly;
- two individually valid values whose sum is just above the remaining allowance.

Avoid unnecessary high-volume traffic. This sprint tests correctness under controlled concurrency, not maximum capacity.

## Per-scenario evidence checklist

Capture:

- scenario ID;
- build/version;
- test identity;
- relevant starting state;
- request identifiers / idempotency keys;
- timestamps precise enough to establish overlap where required;
- sanitized request/response fields;
- final business state;
- counters/limits after execution;
- relevant audit event or log reference;
- outcome and notes.

## Core invariants

Adapt these to the client’s documented rules.

### Limit invariant

> The total committed effect attributable to accepted requests must not exceed the configured business limit for the applicable window.

### Rejection invariant

> A rejected request must not consume allowance or mutate business state unless the product specification explicitly defines a separate reserved/pending state.

### Duplicate invariant

> Multiple deliveries of the same logical action must not create multiple business effects when the contract promises idempotent behavior.

### Recovery invariant

> A retry after an ambiguous client-side outcome must converge to one documented business result rather than duplicate or silently lose the action.

### Audit invariant

> Audit evidence must agree with the committed business state and identify the outcome of each submitted request well enough for independent review.

## Stop conditions

Stop execution and ask for clarification when:

- observed behavior conflicts with undocumented assumptions;
- the environment appears to be production unexpectedly;
- test data contains real customer information not approved for use;
- requested concurrency exceeds the written ceiling;
- a scenario could cause destructive or irreversible effects;
- credentials appear broader than necessary for the scope.
