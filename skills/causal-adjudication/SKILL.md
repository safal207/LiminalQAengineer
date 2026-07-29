---
name: causal-adjudication
description: Convert observations into causal findings while preserving uncertainty, competing explanations, counterfactuals, and responsibility lineage. Use after evidence capture and before severity or remediation claims.
---

# Causal Adjudication

## Core question

Do not ask only, “What failed?” Ask:

> What evidence supports this claim, what caused the observed transition, and what alternative explanation would produce the same signal?

## Claim levels

| Level | Meaning |
| --- | --- |
| `OBSERVATION` | A bounded fact was recorded. |
| `PRODUCT_SIGNAL` | The fact may affect a product or journey. |
| `DEFECT_CANDIDATE` | Expected and actual states conflict under reproducible conditions. |
| `CONFIRMED_DEFECT` | Reproduction, expectation, scope, identity, and causal evidence passed adjudication. |
| `ROOT_CAUSE_HYPOTHESIS` | A plausible mechanism, not yet proven. |
| `CONFIRMED_ROOT_CAUSE` | The mechanism is supported by code/state evidence and a discriminating counterfactual or controlled change. |

Never present a lower level using the language of a higher one.

## Causal graph model

Represent each finding as nodes and typed edges:

```text
INTENT / REQUIREMENT
  -> expected_state

PRECONDITION
  -> enables

ACTION
  -> transitions_to

OBSERVATION
  -> supports | contradicts

CAUSE_CANDIDATE
  -> may_explain

EVIDENCE
  -> supports | weakens | falsifies

IMPACT
  -> affects

RECOVERY
  -> restores | fails_to_restore
```

Each non-root conclusion needs at least one valid parent. A missing or ambiguous parent is a finding, not a blank to be filled by intuition.

## CML checks

Apply these minimum rules:

- `CML-AUDIT-R1-MISSING_PARENT` — a claimed conclusion references a cause that is absent from the trace;
- `CML-AUDIT-R2-GAP_NOT_MARKED` — a causal gap exists but is not explicitly marked;
- `CML-AUDIT-R3-SECRET_NET_MISSING_CHAIN` — secret access and network/send behavior lack a valid responsibility chain;
- `CML-AUDIT-R4-AMBIGUOUS_ROOT` — root authority, intent, or requirement is malformed or ambiguous.

A functionally successful action can still be causally invalid.

## Adjudication procedure

For each finding:

1. State the observation using neutral language.
2. Identify the expected state and its authority: specification, product rule, visible promise, accessibility standard, or consistent prior behavior.
3. Build the shortest causal path from precondition to impact.
4. List at least one realistic competing explanation.
5. Identify evidence that would distinguish the explanations.
6. Run or request the smallest safe discriminating test.
7. Update confidence and claim level without deleting the losing hypothesis from the ledger.

## Counterfactual discipline

A useful counterfactual changes one load-bearing variable:

```text
If cause X were removed while other relevant conditions stayed stable,
would observation Y still occur?
```

Examples:

- same route, different viewport;
- same account, refreshed authorization;
- same data, fixed initialization order;
- same PR, exact head before and after the disputed change;
- same journey, network restored after reconnect.

Do not call an imagined scenario a counterfactual test.

## Temporal rules

Record both:

- `valid_time` — when the product fact was true;
- `transaction_time` — when the audit learned or stored it.

A stale observation can remain historically true but must not be used as proof of the current state without revalidation.

## Severity and confidence

Severity measures plausible impact under the supported scope. Confidence measures evidence strength. Keep them separate.

A high-severity hypothesis with weak evidence remains `NEEDS_EVIDENCE`; it does not become a confirmed critical defect.

## Verdicts

- `ALLOW_REPORT` — the report wording matches the supported claim level.
- `ESCALATE` — semantic expectation, severity, legal meaning, or human authority is unresolved.
- `BLOCK` — evidence, identity, freshness, or causal lineage is insufficient for the requested claim.

The verdict applies to the conclusion, not to deployment, disclosure, merge, or external contact.
