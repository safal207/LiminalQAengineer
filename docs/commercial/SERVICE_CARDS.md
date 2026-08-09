# Commercial Service Cards

These are short client-facing offers. Keep the scope narrow and fixed.

## Critical API Reliability Sprint

**Best for:** payments, transfers, orders, subscriptions, identity, account actions, quotas, or other critical API flows.

**I test:**

- boundary conditions;
- retries and duplicates;
- idempotency;
- timeout handling;
- partial failures;
- state consistency;
- controlled concurrency where approved.

**You receive:**

- test matrix;
- reproducible findings;
- request/response and state evidence;
- severity + business priority;
- one retest pass.

**Typical scope:** one critical flow in test/staging.

**Typical delivery:** 2–4 business days.

**Typical price:** USD 600–1,200 fixed.

**Pitch:**

> Give me one critical API flow in a test environment. I will pressure-test the business boundaries and failure modes that are easiest to miss in normal happy-path QA, then return reproducible evidence and a prioritized fix list.

---

## AI Agent Reliability Sprint

**Best for:** agentic workflows that can call tools, spend budget, mutate state, or require approvals.

**I test:**

- tool-call boundaries;
- approval-chain races;
- quota/spend enforcement;
- retry loops;
- duplicate actions;
- partial failures;
- recovery / safe stop;
- audit-trail consistency.

**You receive:**

- state/failure model;
- controlled test matrix;
- reproducible findings;
- evidence chain;
- business-risk priority;
- one retest pass.

**Typical scope:** one agent workflow using test credentials and test data only.

**Typical delivery:** 2–5 business days.

**Typical price:** USD 750–1,500 fixed.

**Pitch:**

> I do not try to "hack" the agent. I test whether an authorized agent workflow remains inside its expected limits when actions race, retry, fail halfway, or repeat.

---

## Integration Acceptance Sprint

**Best for:** CRM ↔ billing, ERP ↔ warehouse, app ↔ PSP, internal microservices, event-driven flows.

**I test:**

- API/event contracts;
- data mapping;
- status transitions;
- duplicate messages;
- retry/timeouts;
- error propagation;
- eventual consistency;
- acceptance criteria.

**You receive:**

- integration test matrix;
- reproducible failures;
- mapping/contract gaps;
- acceptance summary;
- prioritized next actions.

**Typical delivery:** 3–5 business days.

**Typical price:** USD 800–1,500 fixed.

---

## Product Funnel QA Sprint

**Best for:** landing → lead, onboarding, checkout, renewal, in-app offers, conversion flows.

**I test / analyze:**

- user path friction;
- missing or conflicting states;
- validation and error behavior;
- analytics event coverage;
- drop-off hypotheses;
- acceptance criteria for an improved flow.

**You receive:**

- one-page funnel diagnosis;
- target-state flow;
- QA checklist;
- analytics event map;
- experiment plan.

**Typical delivery:** 3–5 business days.

**Typical price:** USD 600–1,000 fixed.

---

## Release Evidence Pack

**Best for:** high-impact release candidates, AI-generated changes, or teams that need an auditable decision packet.

**I provide:**

- exact build/version identity;
- high-impact regression checks;
- run evidence;
- reproducible findings;
- advisory PASS / WARN / HOLD recommendation;
- retest note.

**Typical delivery:** 1–3 business days.

**Typical price:** USD 500–900 fixed.

---

## Qualification filter

Accept the job when all are true:

```text
AUTHORIZED
+ TEST / STAGING / LOCAL ENVIRONMENT
+ FIXED TARGET
+ FIXED SCOPE
+ EVIDENCE CAN BE COLLECTED SAFELY
+ BUSINESS RULES CAN BE CONFIRMED
```

Do not start when any of these are unclear:

```text
WHO OWNS THE TARGET?
WHAT EXACTLY IS AUTHORIZED?
WHAT IS THE ENVIRONMENT?
WHAT IS OUT OF SCOPE?
WHAT DATA MAY BE USED?
```

The offer is reliability QA, not open-ended offensive security.
