# QA Sprint Kit v1

Evidence-driven fixed-scope QA for critical API, AI-agent, integration, and product workflows.

## Positioning

LiminalQA does not sell an open-ended "QA engineer by the hour" engagement.

The default commercial unit is a **small, fixed-scope reliability sprint**:

```text
AUTHORIZED TEST SCOPE
        ↓
CRITICAL USER / SYSTEM FLOW
        ↓
STATE + FAILURE MODEL
        ↓
CONTROLLED EXECUTION
        ↓
REPRODUCIBLE EVIDENCE
        ↓
FINDINGS + BUSINESS IMPACT
        ↓
FIX
        ↓
ONE RETEST PASS
```

The goal is to answer one practical question quickly:

> Can this critical flow fail, double-execute, violate a business limit, lose state, or leave an inconsistent result under realistic edge conditions?

## Safety boundary

Every sprint is fail-closed before execution.

Accepted environments:

- client-owned test or staging systems;
- explicit written authorization for the exact target and endpoints;
- test-mode API keys and synthetic/test data;
- repository-local fixtures;
- local emulators or private sandboxes;
- local smart-contract test projects or explicitly authorized local forks.

Default exclusions:

- production access unless separately and explicitly authorized in writing;
- real customer secrets or unnecessary personal data;
- public infrastructure scanning;
- credential attacks;
- account takeover attempts;
- exploit chaining against third-party systems;
- mainnet/public-testnet attack execution;
- persistence, malware, or destructive testing.

If scope, ownership, or authorization is unclear, execution does not start.

## Standard sprint packages

### 1. Critical API Reliability Sprint

Typical scope:

- one critical API workflow;
- happy path and boundary cases;
- duplicate / retry behavior;
- idempotency where applicable;
- timeout and partial-failure handling;
- state consistency after rejected or interrupted requests;
- limited concurrency against the same logical resource;
- one retest pass for confirmed fixes.

Typical delivery window: **2–4 business days**.

Typical commercial range: **USD 600–1,200 fixed**.

### 2. AI Agent Reliability Sprint

Typical scope:

- tool-call boundaries;
- approval-chain behavior;
- spend / quota limits;
- retry loops and duplicate actions;
- stale-state handling;
- partial failures;
- audit-trail consistency;
- recovery and safe-stop behavior.

Execution must use a controlled test environment and explicitly approved test identities or credentials.

Typical delivery window: **2–5 business days**.

Typical commercial range: **USD 750–1,500 fixed**.

### 3. Integration Acceptance Sprint

Typical scope:

- one integration path between two or more systems;
- request/response contract checks;
- mapping and validation rules;
- retry and timeout semantics;
- duplicate-event handling;
- asynchronous status convergence;
- error propagation;
- acceptance evidence.

Typical delivery window: **3–5 business days**.

Typical commercial range: **USD 800–1,500 fixed**.

### 4. Product Funnel QA Sprint

Typical scope:

- one acquisition, onboarding, payment, or conversion flow;
- friction and drop-off hypotheses;
- form and state validation;
- edge-case UX behavior;
- analytics event map;
- acceptance criteria for the proposed change;
- small experiment / A-B test plan where appropriate.

Typical delivery window: **3–5 business days**.

Typical commercial range: **USD 600–1,000 fixed**.

### 5. Release Evidence Pack

Typical scope:

- one release candidate or one critical change set;
- exact version/build identity;
- high-impact regression checklist;
- evidence-backed run summary;
- reproducible findings;
- release HOLD / WARN / PASS recommendation as advisory output;
- one retest pass.

Typical delivery window: **1–3 business days**.

Typical commercial range: **USD 500–900 fixed**.

## Scope intake

A sprint starts only after these fields are frozen:

| Field | Required |
|---|---|
| Client / system owner | yes |
| Environment | yes |
| Written authorization boundary | yes |
| In-scope endpoints / flows | yes |
| Out-of-scope areas | yes |
| Test credentials source | yes |
| Data policy | yes |
| Expected business rules | yes |
| Limits / quotas / time windows | when applicable |
| Allowed concurrency / load | when applicable |
| Delivery deadline | yes |
| Retest terms | yes |

Use `SCOPE_TEMPLATE.md` for the client-facing version.

## Core test lenses

### State

For every important action, record:

```text
pre-state
  ↓
action
  ↓
response / event
  ↓
post-state
  ↓
subsequent observable state
```

### Boundary

Examples:

- below threshold;
- exactly at threshold;
- above threshold;
- zero / empty / missing where valid to test;
- last valid time / first invalid time;
- first request / duplicate request;
- accepted request / rejected request.

### Retry and duplication

Questions:

- Can the same business action be applied twice?
- Does a retry after timeout replay safely?
- Do duplicate identifiers produce one logical result?
- Are counters, balances, quotas, or states updated once?

### Partial failure

Questions:

- What happens if step 1 succeeds and step 2 fails?
- Does the workflow compensate, recover, or expose a clear pending state?
- Are status, accounting, and audit records consistent?

### Controlled concurrency

Questions:

- Can simultaneous requests exceed a business limit?
- Is final state deterministic enough to explain?
- Does one accepted action cause later conflicting actions to reject cleanly?
- Are counters and side effects atomic at the business level?

### Auditability

Questions:

- Can a client reproduce the finding?
- Is the exact request / build / environment identified?
- Are timestamps and relevant state transitions captured?
- Can a retest prove the fix rather than merely repeat the claim?

## Standard deliverables

Every sprint returns:

1. **Scope snapshot** — what was and was not tested.
2. **Test matrix** — scenarios, expected outcomes, actual outcomes.
3. **Findings** — reproducible evidence and impact.
4. **Run summary** — what passed, failed, was blocked, or remained inconclusive.
5. **Business-priority view** — fix now / next / monitor.
6. **Retest note** — one verification pass for confirmed fixes when included.

Recommended folder shape:

```text
engagement/
  scope.md
  test-matrix.md
  run-summary.md
  findings/
    F-001.md
    F-002.md
  evidence/
    request-response/
    logs/
    screenshots/
    state/
  retest.md
```

## Finding format

Each finding follows:

```text
Finding
  ↓
Preconditions
  ↓
Action path
  ↓
Observed result
  ↓
Expected result
  ↓
Evidence
  ↓
Business impact
  ↓
Severity / priority
  ↓
Suggested acceptance criterion
  ↓
Retest
```

Use `FINDING_TEMPLATE.md`.

## Severity and priority

Severity is based on demonstrated impact in the authorized environment, not on dramatic wording.

Suggested levels:

- **Critical** — demonstrated catastrophic business impact in scope, requiring immediate stop.
- **High** — major loss, duplicate execution, severe integrity failure, or broad critical-flow outage.
- **Medium** — meaningful business-rule, consistency, recovery, or workflow failure with a realistic trigger.
- **Low** — limited impact, minor integrity issue, or edge-case defect with constrained consequence.
- **Observation** — improvement opportunity without demonstrated defect.

Separately mark delivery priority:

- `P0 fix before release`
- `P1 fix next`
- `P2 schedule`
- `P3 monitor`

## Exit semantics

A sprint should never convert missing evidence into success.

Use explicit outcomes:

- `PASS` — tested behavior matched the agreed rule within the agreed scope;
- `FAIL` — reproducible deviation found;
- `BLOCKED` — execution could not be completed because of access, environment, or dependency;
- `INCONCLUSIVE` — evidence is insufficient to make the requested determination.

## Commercial conversation script

Short version:

> I suggest we do not start with an open-ended QA engagement. Give me one critical flow in a test environment. I will freeze the scope, test the highest-risk state transitions and failure modes, and return reproducible evidence, business-priority findings, and one retest pass. That gives you a concrete decision in a few days before deciding on broader work.

## Discovery call checklist

Ask:

1. What is the one flow you are most afraid of breaking?
2. What would a financially or operationally wrong result look like?
3. Which limits, statuses, approvals, or time windows govern that flow?
4. What retries or duplicate requests are expected?
5. Which step can partially fail?
6. What test environment and test identities are available?
7. What is explicitly out of scope?
8. What evidence does the team need to trust a finding?
9. Who confirms expected behavior when documentation is ambiguous?
10. What fix/retest deadline matters?

## LiminalQA operating model

```text
CLIENT SCOPE
      ↓
GUIDANCE
business invariant / expected outcome
      ↓
CO-NAVIGATION
controlled execution + retries + boundaries
      ↓
INNER COUNCIL
API / state / logs / UI / events reconciled
      ↓
REFLECTION
cause → evidence → impact → next action
```

Where the wider Neo Rezonans stack is available:

```text
LiminalOSAI  → authority / execution boundary
LiminalQA    → test orchestration + triage
LiminalDB    → state + temporal evidence
RINSE        → retrospective verification loop
ProofPath    → evidence chain / provenance
ContractGraph-QA → smart-contract state-path engagements
```

The commercial promise remains narrow:

> **One critical flow. One frozen scope. Reproducible evidence. A decision the client can act on.**
