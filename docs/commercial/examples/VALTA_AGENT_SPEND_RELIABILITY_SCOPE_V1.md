# Valta Agent Spend Reliability Sprint — Scope v1

Status: **pre-execution / awaiting final client confirmation and test access**

This document converts the agreed commercial discussion into a frozen, safety-bounded QA scope. It is not authorization to test production systems and must not be treated as such.

## 1. Engagement objective

Independently pressure-test spend-limit enforcement and accounting consistency under controlled concurrency in Valta's **test-mode environment**.

Primary question:

> Can simultaneous or retried spend requests against the same test wallet cause per-transaction, daily, or monthly limits to be exceeded, counted inconsistently, or leave spend state inconsistent after a rejected or partial request?

## 2. Commercial frame

Proposed first sprint:

- fixed scope;
- fixed price: **USD 750**;
- target delivery: **2 business days** after receipt of test access, API documentation, and final written scope confirmation;
- one retest pass for confirmed fixes within the original scope.

No work starts until the client confirms the final endpoints, test credentials flow, applicable limit rules, and safe concurrency ceiling.

## 3. Authorization and safety boundary

### Allowed

- client-provided test-mode API key;
- client-designated test/staging endpoints only;
- client-designated test wallets/accounts only;
- synthetic or client-approved test data;
- bounded concurrency within the ceiling approved by the client;
- ordinary API requests needed to exercise the in-scope spend workflow;
- collection of request/response, timing, status, and test-state evidence.

### Not allowed

- production credentials;
- production endpoints;
- real user data;
- real funds;
- public-infrastructure scanning;
- authentication bypass;
- credential guessing, harvesting, or reuse;
- destructive or denial-of-service testing;
- persistence, malware, or code execution outside the documented test interface;
- third-party targets or dependencies not explicitly included by the client;
- load levels beyond the approved ceiling.

If an in-scope test unexpectedly touches production, real user data, real funds, or an undeclared third party, execution stops immediately and the sprint is placed on **HOLD** pending client guidance.

## 4. In-scope functional surface

Final endpoint names remain **TBD by client**.

Expected in-scope operations:

1. create/submit a spend attempt;
2. obtain spend result/status;
3. observe relevant limit state or approved equivalent evidence;
4. observe final wallet/accounting state or approved equivalent evidence.

Client to confirm:

- spend endpoint(s): `TBD`;
- status/read endpoint(s): `TBD`;
- wallet/account identifier model: `TBD`;
- idempotency/request identifier mechanism: `TBD`;
- spend-counter observability mechanism: `TBD`;
- audit/event/log observability mechanism, if exposed to the test client: `TBD`.

## 5. Business rules to freeze before execution

Client must provide or confirm the exact expected rules for:

- per-transaction cap;
- daily cap;
- monthly cap;
- timezone and reset boundary for daily limits;
- timezone/date boundary for monthly limits;
- whether pending requests reserve limit capacity;
- whether rejected requests affect counters;
- whether failed/rolled-back requests affect counters;
- idempotency semantics;
- duplicate request semantics;
- timeout/retry semantics;
- partial-failure semantics;
- expected final status vocabulary.

Example values used during planning are illustrative only and must not be treated as client rules.

## 6. Core test matrix

### V-01 — per-transaction below limit

Precondition: available daily/monthly capacity.

Action: submit one spend below the per-transaction cap.

Expected: accepted according to documented business rules; exactly one accounting effect.

### V-02 — per-transaction at limit

Action: submit one spend exactly equal to the cap.

Expected: deterministic handling matching the documented boundary rule.

### V-03 — per-transaction above limit

Action: submit one spend above the cap.

Expected: rejected; no spend-counter or wallet-state side effect unless explicitly documented otherwise.

### V-04 — concurrent requests jointly exceed remaining daily capacity

Example shape only:

- remaining daily capacity: 10 units;
- request A: 6 units;
- request B: 6 units;
- both launched concurrently against the same test wallet.

Expected: final accepted total never exceeds the documented daily cap.

### V-05 — concurrent requests jointly exceed remaining monthly capacity

Same structure as V-04, applied to the monthly limit.

### V-06 — per-transaction passes while daily limit denies

Expected: the stricter applicable aggregate rule is enforced without inconsistent partial accounting.

### V-07 — daily passes while monthly limit denies

Expected: monthly cap is enforced atomically.

### V-08 — burst at the limit boundary

Client-approved bounded burst of simultaneous spend attempts against one test wallet.

Expected:

- accepted amount/count matches available capacity;
- rejected amount/count is deterministic or explainably non-deterministic within documented rules;
- total accepted spend does not exceed the cap;
- no hidden double-counting.

### V-09 — duplicate request with same idempotency identity

Expected: no duplicate financial/accounting effect.

### V-10 — retry after client-visible timeout

Only if the test environment provides a safe way to reproduce a timeout or delayed response without exceeding the approved test boundary.

Expected: retry does not produce unintended duplicate spend/accounting.

### V-11 — rejected request leaves clean state

Expected: limit counters, wallet state, request status, and audit state remain mutually consistent.

### V-12 — partial-failure recovery

Only if Valta provides a documented test-mode mechanism or fixture for an in-scope partial failure.

Expected: final state follows the documented rollback/compensation semantics; no silent limit leakage or double reservation.

### V-13 — sequential control case

Repeat representative requests sequentially to distinguish concurrency-specific defects from ordinary rule errors.

### V-14 — post-burst reconciliation

After a bounded concurrent test, compare:

- accepted requests;
- rejected requests;
- observed spend total;
- remaining limit capacity;
- final wallet/account state;
- audit/status evidence available to the tester.

Expected: all observable representations reconcile.

## 7. Concurrency model

The tester will not choose an arbitrary load level.

Before execution, Valta must approve:

- maximum concurrent requests per test case: `TBD`;
- maximum requests per second, if applicable: `TBD`;
- maximum total requests in the sprint: `TBD`;
- any backoff between cases: `TBD`;
- reset/cleanup process for test wallets: `TBD`.

The objective is correctness under **controlled concurrency**, not performance benchmarking or stress/DoS testing.

## 8. Evidence captured per case

Where available and safe to retain:

- case ID;
- UTC timestamp;
- test environment identifier;
- sanitized request payload or request fingerprint;
- request/idempotency identifier;
- start/end timing;
- HTTP/status result;
- sanitized response body or response fingerprint;
- observed counter/limit state before and after;
- observed wallet/account state before and after;
- accepted/rejected totals;
- reconciliation notes;
- expected vs actual result.

Secrets, API keys, authorization headers, personal data, and unrelated client data must not be stored in the evidence pack.

## 9. Finding format

Each finding must contain:

1. title;
2. severity;
3. confidence;
4. affected business rule;
5. preconditions;
6. minimal reproduction;
7. expected result;
8. observed result;
9. state before/after;
10. evidence references;
11. business impact;
12. recommended acceptance criterion;
13. retest result, when applicable.

A reproducible anomaly is reported as an observed QA finding. Security classification is only applied if the client explicitly requests it and the demonstrated evidence supports that classification.

## 10. Severity guidance

### P0 — Critical

Demonstrated test-mode behavior implying an uncontrolled spend/accounting failure with severe direct business impact and a clear production-relevant path, subject to client confirmation.

### P1 — High

Reproducible limit bypass, double accounting, or material state inconsistency in the in-scope workflow.

### P2 — Medium

Important inconsistency, retry/idempotency defect, or boundary error with bounded impact or additional preconditions.

### P3 — Low

Minor correctness, observability, or contract-quality issue that does not materially change spend enforcement.

Severity remains provisional until business impact is confirmed with the client.

## 11. Deliverables

Client receives:

- final frozen scope;
- concise test matrix;
- execution summary;
- reproducible findings;
- sanitized evidence references;
- severity and business-risk priority;
- expected-vs-actual notes;
- one retest pass for fixes delivered within the sprint window;
- final status: `PASS`, `PASS_WITH_FINDINGS`, `HOLD`, or `INCOMPLETE`.

## 12. Exit semantics

### PASS

All executed in-scope cases meet the frozen expected behavior and evidence is sufficient.

### PASS_WITH_FINDINGS

Execution completed and one or more findings remain documented.

### HOLD

Testing stops because authorization, environment identity, data boundary, concurrency ceiling, or another safety condition is unclear.

### INCOMPLETE

The sprint could not fully execute because required access, documentation, observability, test fixtures, or client-confirmed business rules were unavailable.

`INCOMPLETE` must never be converted into `PASS`.

## 13. Required client confirmation before start

Valta should confirm the following in writing:

- [ ] test/staging base URL(s);
- [ ] test credential issuance process;
- [ ] test wallet/account identifiers;
- [ ] spend endpoint(s);
- [ ] status/read endpoint(s);
- [ ] exact per-transaction limit rule;
- [ ] exact daily limit rule and reset boundary;
- [ ] exact monthly limit rule and reset boundary;
- [ ] idempotency/duplicate semantics;
- [ ] partial-failure test mechanism, if any;
- [ ] approved concurrency ceiling;
- [ ] permitted evidence fields;
- [ ] confirmation that no production access, real user data, or real funds are required;
- [ ] confirmation that the fixed scope above is authorized for execution.

## 14. Operator start gate

Execution may begin only when all of the following are true:

```text
written scope confirmed
        +
test environment identified
        +
test credentials received
        +
business rules frozen
        +
concurrency ceiling approved
        +
evidence boundary confirmed
```

Otherwise the engagement remains **NOT STARTED**.
