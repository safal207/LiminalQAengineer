# Valta Agent Spend Reliability Sprint — Client Start Confirmation

Use this as the final written start gate before execution.

Status until completed: **NOT STARTED**

## Commercial scope

Engagement: **Valta Agent Spend Reliability Sprint**

Fixed price: **USD 750**

Target delivery: **initial execution + report within 2 business days after all start-gate inputs are received and confirmed**.

Included:

- concurrent spend attempts against the same designated test wallet/account;
- per-transaction, daily, and monthly cap enforcement under controlled concurrency;
- boundary/race cases where simultaneous requests together cross a frozen limit;
- duplicate/idempotency behavior relevant to limit accounting;
- retry behavior only where a safe test-mode fixture/condition is provided;
- partial-failure consistency only where a client-provided test-mode mechanism exists;
- sanitized reproducible evidence;
- severity/business-risk priority;
- one retest pass for confirmed fixes inside the original scope.

## Please confirm in writing

### 1. Environment and authorization

- [ ] The supplied base URL(s) are test/staging only.
- [ ] The supplied credentials are test-mode only and do not grant production access.
- [ ] The supplied wallets/accounts are designated test entities.
- [ ] No real user data is required.
- [ ] No real funds are required.
- [ ] Valta authorizes the fixed scope above against the named test environment.

Base URL(s): `TBD`

Environment name: `TBD`

Test wallet/account identifiers or aliases: `TBD`

Credential issuance method: `TBD`

### 2. In-scope endpoints

Submit spend: `TBD`

Read spend/result: `TBD`

Read wallet/account state: `TBD`

Read limit/counter state or approved equivalent: `TBD`

Audit/event/log view, if available: `TBD`

Idempotency/request identity mechanism: `TBD`

### 3. Frozen limit rules

Per-transaction cap: `TBD`

Exact-boundary rule: `TBD`

Daily cap: `TBD`

Daily reset timezone/boundary: `TBD`

Monthly cap: `TBD`

Monthly reset timezone/boundary: `TBD`

Pending request reservation behavior: `TBD`

Rejected request counter behavior: `TBD`

Failed/rolled-back request counter behavior: `TBD`

Duplicate/idempotency semantics: `TBD`

Retry semantics: `TBD`

Partial-failure/compensation semantics: `TBD / not available`

### 4. Controlled concurrency ceiling

Maximum simultaneous requests per case: `TBD`

Maximum requests/second, if relevant: `TBD`

Maximum requests per case: `TBD`

Maximum total test requests in the sprint: `TBD`

Required cooldown/backoff: `TBD`

The sprint tests correctness under bounded concurrency. It is not a stress/DoS or capacity benchmark.

### 5. Evidence boundary

Please confirm what may be retained in the final evidence pack:

- [ ] sanitized request payloads;
- [ ] sanitized response payloads;
- [ ] request IDs;
- [ ] idempotency keys;
- [ ] UTC timing data;
- [ ] wallet/account aliases or hashes;
- [ ] limit/counter values;
- [ ] audit/event IDs.

Any additional redaction requirements: `TBD`

Secrets, API keys and Authorization headers will never be retained in the evidence pack.

## Start decision

Execution starts only after the fields above are sufficiently complete to state expected behavior before each test and Valta confirms authorization for the frozen test scope.

Client confirmation:

```text
I confirm the test/staging environment, business rules, approved concurrency ceiling,
evidence boundary, and authorization for the Valta Agent Spend Reliability Sprint
as described above.

Name: ____________________
Role: ____________________
Date: ____________________
```

Email confirmation containing the same facts is sufficient; a signature is not required unless Valta's own process requires one.

## Operator response after confirmation

Once confirmed, the operator records:

```text
ENGAGEMENT: VALTA-ASR-001
STATUS: START AUTHORIZED
ENVIRONMENT: <name>
UTC START: <timestamp>
SCOPE VERSION: <confirmed version>
CONCURRENCY CEILING: <value>
EVIDENCE BOUNDARY: <summary>
```

If any safety/authorization condition changes during execution, the sprint moves to `HOLD` until re-confirmed.
