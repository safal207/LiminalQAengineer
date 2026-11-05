# Valta Agent Spend Reliability Sprint — Execution Pack v1

Status: **READY TO INTAKE / NOT STARTED**

This pack is the operator-facing companion to `../VALTA_AGENT_SPEND_RELIABILITY_SCOPE_V1.md`.
It converts the frozen commercial scope into a repeatable execution sequence. It does **not** authorize testing by itself.

## 0. Start gate

Do not execute any test request until all six conditions are true:

```text
written scope confirmed
+ test/staging base URL confirmed
+ test-mode credentials received
+ exact limit rules frozen
+ concurrency ceiling approved
+ evidence boundary confirmed
= START AUTHORIZED
```

If any item is missing, status remains `NOT STARTED`.

Immediate HOLD triggers:

- endpoint resolves to production;
- credential has production privileges;
- real user data appears;
- real funds or production wallet are involved;
- an undeclared third-party target is required;
- requested concurrency exceeds the client-approved ceiling;
- business rule is ambiguous enough that expected behavior cannot be stated before execution.

## 1. Client intake sheet

Fill these fields before the first request.

### Environment

- Engagement ID: `VALTA-ASR-001`
- Environment name: `TBD`
- Base URL: `TBD`
- Environment owner/contact: `TBD`
- Environment identity proof: `TBD`
- Test credential issuance method: `TBD`
- Credential expiry: `TBD`
- Test wallet/account IDs: `TBD`
- Test data reset method: `TBD`

### In-scope API surface

- Submit spend endpoint: `TBD`
- Read spend/result endpoint: `TBD`
- Read wallet/account state endpoint: `TBD`
- Read limit/counter state endpoint or approved equivalent: `TBD`
- Audit/event/log endpoint or approved equivalent: `TBD`
- Idempotency header/field: `TBD`
- Client request ID/header: `TBD`

### Frozen business rules

- Per-transaction cap: `TBD`
- Per-transaction boundary behavior (`<`, `<=`): `TBD`
- Daily cap: `TBD`
- Daily reset timezone: `TBD`
- Daily reset boundary: `TBD`
- Monthly cap: `TBD`
- Monthly reset timezone: `TBD`
- Monthly reset boundary: `TBD`
- Pending request reservation semantics: `TBD`
- Rejected request counter semantics: `TBD`
- Failed request counter semantics: `TBD`
- Idempotency semantics: `TBD`
- Duplicate request semantics: `TBD`
- Client-visible timeout semantics: `TBD`
- Retry semantics: `TBD`
- Partial failure / compensation semantics: `TBD`
- Final status vocabulary: `TBD`

### Approved execution ceiling

- Max simultaneous requests per case: `TBD`
- Max requests per second: `TBD`
- Max requests per case: `TBD`
- Max total requests in sprint: `TBD`
- Required cooldown/backoff: `TBD`
- Any time windows to avoid: `TBD`

### Evidence rules

Allowed to retain:

- sanitized request body: `YES / NO / CONDITIONS`
- response body: `YES / NO / CONDITIONS`
- request ID: `YES / NO`
- idempotency key: `YES / NO`
- timing: `YES / NO`
- wallet/account ID: `YES / NO / HASH ONLY`
- counter values: `YES / NO`
- audit/event IDs: `YES / NO`

Never retain:

- API keys;
- Authorization headers;
- real personal data;
- unrelated client data;
- secrets/tokens returned by the platform.

## 2. Test data design

Use dedicated test wallets/accounts so cases can be reset or isolated.

Recommended allocation:

- `W-CONTROL` — sequential baseline;
- `W-PERTX` — per-transaction boundary;
- `W-DAILY` — daily-cap concurrency;
- `W-MONTHLY` — monthly-cap concurrency;
- `W-IDEMP` — duplicate/idempotency;
- `W-RETRY` — retry/timeout, only if client provides a safe fixture;
- `W-PARTIAL` — partial-failure fixture, only if client provides one;
- `W-BURST` — bounded burst/reconciliation.

If wallet isolation is unavailable, document reset steps and state preconditions before every case.

## 3. Execution order

Run from lowest-risk controls to concurrency-sensitive cases.

```text
Phase 1 — Environment identity + read-only checks
Phase 2 — Sequential baseline
Phase 3 — Single-request boundaries
Phase 4 — Controlled concurrency at daily/monthly boundaries
Phase 5 — Idempotency / duplicate behavior
Phase 6 — Retry / timeout fixture (if supplied)
Phase 7 — Partial-failure fixture (if supplied)
Phase 8 — Client-approved bounded burst
Phase 9 — Reconciliation
Phase 10 — Findings + retest queue
```

Do not jump directly to burst/concurrency testing before sequential expected behavior is established.

## 4. Phase 1 — preflight

Record:

1. base URL and environment identity;
2. credential class = test mode;
3. test wallet/account identity;
4. current wallet/account state;
5. current daily/monthly counters;
6. current time and the timezone used by limit resets;
7. confirmed concurrency ceiling;
8. evidence fields permitted by client.

Preflight outcome:

- `READY` — all observable values consistent with frozen scope;
- `HOLD` — environment/authorization/data boundary unclear;
- `INCOMPLETE` — required observability missing.

## 5. Phase 2 — sequential control

Purpose: establish ordinary business-rule behavior before looking for race-specific defects.

Minimum controls:

- spend below per-tx cap;
- spend exactly at per-tx boundary;
- spend above per-tx cap;
- request that passes per-tx but fails daily;
- request that passes per-tx/daily but fails monthly, where practical.

For every control capture:

- state before;
- request identity;
- expected result;
- HTTP/application result;
- state after;
- counter delta;
- wallet/account delta;
- audit/status delta.

If sequential controls already violate the frozen rules, log the finding before continuing. Concurrency cases may still run if the defect does not invalidate their preconditions.

## 6. Phase 3 — concurrency cases

All simultaneous requests must target the same designated test wallet/account and remain within the approved ceiling.

### C-DAY-01 — remaining daily capacity race

Precondition example only:

```text
daily cap = D
already spent = S
remaining = R = D - S
request A = A
request B = B
A <= R
B <= R
A + B > R
```

Launch A and B as close together as the agreed client/test tooling permits.

Primary invariant:

```text
final accepted spend <= D
```

Secondary invariants:

- rejected requests do not produce hidden wallet movement;
- counters reconcile to accepted effects;
- final statuses reconcile with wallet/counter state;
- no request is applied twice.

### C-MONTH-01 — remaining monthly capacity race

Same structure as C-DAY-01, applied to the monthly limit.

Primary invariant:

```text
final accepted spend <= monthly cap
```

### C-PERTX-01 — simultaneous requests near per-tx cap

Purpose: confirm that per-request validation remains correct under simultaneous arrival and does not become dependent on shared aggregate-state races.

### C-BURST-01 — bounded burst

Only after client approves an exact request count/concurrency level.

Capture:

- total attempts;
- total accepted;
- total rejected;
- accepted amount sum;
- rejected amount sum;
- final counters;
- final wallet/account state;
- any status/audit mismatch.

This is a correctness test, not a throughput benchmark or denial-of-service test.

## 7. Phase 4 — duplicate and idempotency

### I-01 — same idempotency identity, same payload

Expected according to frozen client semantics, with the key invariant:

```text
at most one financial/accounting effect for one logical request
```

### I-02 — same idempotency identity, repeated after original response

Capture response/status relationship and final accounting state.

### I-03 — same idempotency identity while original request is still pending

Run only if the client confirms this timing is safe and expected behavior is documented.

### I-04 — same logical request with a new client request ID

This is not automatically a duplicate. Record behavior only against the client-provided contract; do not infer intended semantics.

## 8. Phase 5 — timeout / retry

Run **only** with a client-provided safe test mechanism, delayed fixture, or documented test-mode behavior.

Do not intentionally degrade or interfere with production/public infrastructure to manufacture a timeout.

Test question:

> If the server processed the original logical spend but the client did not receive the response, can the documented retry path create a second effect or inconsistent limit accounting?

Evidence must distinguish:

- first request accepted but response lost/delayed;
- first request not processed;
- first request status unknown;
- retry accepted/rejected/replayed;
- final wallet/counter state.

## 9. Phase 6 — partial failure

Run only if Valta supplies an explicit test fixture or fault-injection mechanism within the authorized environment.

Check consistency between, as observable:

- request status;
- spend/ledger effect;
- daily/monthly counter;
- wallet/account balance/state;
- audit/event trail.

Core invariant:

```text
no silent state where financial effect and enforcement accounting disagree
```

If compensation is asynchronous, record the allowed recovery window before execution and observe only within that window.

## 10. Evidence naming

Use deterministic case folders:

```text
evidence/
  PRE-001/
  S-PERTX-001/
  C-DAY-001/
  C-MONTH-001/
  I-001/
  R-001/
  P-001/
  REC-001/
```

Suggested artifacts per case:

```text
case.md
before.json             # sanitized, only if allowed
requests.jsonl          # sanitized or fingerprints
responses.jsonl         # sanitized or fingerprints
timing.csv
state-after.json        # sanitized, only if allowed
reconciliation.md
```

If raw payload retention is not allowed, store SHA-256 fingerprints plus the safe metadata needed to reproduce the case.

## 11. Run ledger

Use `RUN_LEDGER_TEMPLATE.csv` as the canonical case register.

Required fields:

- case ID;
- UTC start/end;
- environment;
- wallet alias;
- precondition summary;
- expected result;
- observed result;
- accepted/rejected count;
- accepted amount;
- before/after counter summary;
- evidence folder;
- outcome;
- finding ID, if any.

Outcome vocabulary:

- `PASS`
- `FAIL`
- `BLOCKED`
- `NOT_RUN`
- `INCONCLUSIVE`

`NOT_RUN` and `INCONCLUSIVE` never become PASS.

## 12. Finding threshold

Open a finding when at least one is true:

- accepted spend exceeds a frozen cap;
- duplicate/retry creates more than one financial/accounting effect for one logical request where idempotency should prevent it;
- rejected request changes spend/wallet state contrary to the frozen rule;
- counter and wallet/ledger state fail to reconcile;
- final status contradicts the observed financial/accounting state;
- partial failure leaves an inconsistent state beyond the documented recovery window;
- concurrency produces a reproducible business-rule violation not present sequentially.

Use the generic `../../FINDING_TEMPLATE.md` and link every claim to sanitized evidence.

## 13. Severity calibration

Use severity only after demonstrated impact is clear.

- `P0 Critical` — severe uncontrolled spend/accounting failure with clear client-confirmed production relevance.
- `P1 High` — reproducible limit bypass, duplicate financial effect, or material accounting inconsistency.
- `P2 Medium` — important retry/idempotency/boundary inconsistency with bounded impact or additional preconditions.
- `P3 Low` — minor correctness or observability defect with no material limit bypass.

If business impact is uncertain, reduce confidence rather than inflating severity.

## 14. Reconciliation gate

At the end of every concurrency group, reconcile:

```text
sum(accepted financial effects)
== observed wallet/ledger movement
== enforcement counter delta
== accepted request/status set
```

Adjust only for explicitly documented asynchronous behavior, fees, reservations, or compensation semantics.

Any unexplained mismatch creates either:

- a finding; or
- `INCONCLUSIVE` if required observability is missing.

## 15. Stop rules during execution

Stop the active case immediately if:

- the approved concurrency/request ceiling would be exceeded;
- production/real data/real funds appear;
- an endpoint redirects or resolves outside the frozen target;
- a case causes unexpected environment instability;
- the client requests a stop;
- evidence suggests the next step would require testing an undeclared dependency or bypassing an access boundary.

Preserve already collected safe evidence and mark the case `BLOCKED` or the sprint `HOLD`.

## 16. Daily operator sequence

### Day 1

1. freeze scope and intake;
2. preflight;
3. sequential controls;
4. daily/monthly concurrency cases;
5. initial reconciliation;
6. triage findings and request clarification only where evidence requires it.

### Day 2

1. duplicate/idempotency cases;
2. retry/partial-failure fixtures if supplied;
3. bounded burst if approved;
4. final reconciliation;
5. reproduce each candidate finding minimally;
6. write report;
7. package evidence references;
8. deliver findings and retest queue.

The two-day target starts only after the agreed start gate is satisfied.

## 17. Client report assembly

Use `../../REPORT_TEMPLATE.md` and populate from the run ledger.

Recommended first page:

```text
Engagement: Valta Agent Spend Reliability Sprint
Scope: concurrent spend + per-tx/daily/monthly limit enforcement
Environment: <test env>
Execution window: <UTC>
Cases: <n>
Passed: <n>
Findings: <n>
Blocked/Not Run: <n>
Overall: PASS | PASS_WITH_FINDINGS | HOLD | INCOMPLETE
```

Then include:

1. scope and authorization boundary;
2. frozen business rules;
3. executed matrix;
4. findings ordered by business risk;
5. reconciliation summary;
6. limitations / not-run cases;
7. retest queue.

## 18. Retest gate

Retest only:

- confirmed fixes;
- within the original frozen scope;
- in the same authorized test environment or a client-confirmed equivalent;
- with the same or explicitly updated business rule;
- under the same or lower approved concurrency ceiling unless Valta explicitly approves a change.

Per finding record:

```text
NOT_RETESTED
FIX_CONFIRMED
PARTIALLY_FIXED
STILL_REPRODUCIBLE
CANNOT_RETEST
```

## 19. Completion definition

The sprint is complete when:

- all runnable in-scope cases are executed or explicitly classified;
- every result has evidence or a documented evidence limitation;
- all candidate anomalies are either reproduced into findings or marked inconclusive;
- reconciliation is complete;
- report is delivered;
- one retest pass is reserved for fixes within scope.

Final sprint status remains one of:

`PASS`, `PASS_WITH_FINDINGS`, `HOLD`, `INCOMPLETE`.
