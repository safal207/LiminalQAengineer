---
name: causal-deep-audit
description: Orchestrate evidence-first audits across public products, repositories, pull requests, UX flows, content, conversion paths, and agent actions using the connected Liminal repositories. Use when the user asks for a deep audit, causal audit, multi-lens review, or a combined QA/product/business assessment.
---

# Causal Deep Audit

## Purpose

Produce a defensible audit in which every conclusion can be walked backward to an observation, every observation is bound to scope and time, and uncertainty is preserved instead of polished away.

## Required inputs

Resolve from the request or repository context:

- target and canonical origin or repository;
- public surface, authenticated surface, code, PR, or mixed scope;
- authorization boundary;
- exact commit SHA when code or a PR is evaluated;
- device, locale, account, and environment profiles;
- business goal or user journey being protected;
- prohibited actions and stop conditions.

Do not invent missing authorization. Narrow the audit instead.

## Execution graph

### 0. Readiness and authority

Apply the IFP/TIP boundary:

```text
Undefined -> Configured -> Feedback Received -> Corrected -> Ready
```

Record the exact ready state. If target, authority, identity, or environment is ambiguous, return `BLOCKED_BY_BOUNDARY` or `NEEDS_EVIDENCE` for the affected branch.

### 1. Capture signals

Invoke `evidence-capture`.

Collect source, rendered, runtime, accessibility, network, console, temporal, and journey evidence only inside the declared boundary. Build a T-Trace-compatible ordered observation sequence.

### 2. Adjudicate causality

Invoke `causal-adjudication`.

Separate:

```text
observation -> product signal -> defect candidate -> confirmed defect
```

Root cause remains a hypothesis until supported by code, reproducible state transition, or discriminating counterfactual evidence.

### 3. Freeze repository identity

When a repository or pull request is in scope, invoke `exact-head-governance`.

Initial and final head identity must match. A force-push, stale review, unavailable check, or partial collection cannot produce `PASS` or `CONFIRMED_DEFECT` for code-level claims.

### 4. Gate the conclusion

Apply the Pythia boundary:

- `ALLOW_REPORT` — evidence supports the stated claim inside scope;
- `ESCALATE` — a human semantic, legal, product, or severity decision is required;
- `BLOCK` — authority, identity, freshness, or evidence requirements failed.

The gate authorizes a report state, not execution, deployment, contact, disclosure, or merge.

### 5. Retrieve and replay memory

Invoke `replay-memory`.

Use prior audits to find analogous failure patterns and successful discriminating tests. Memory is advisory and may not override current exact evidence.

### 6. Model user and business impact

Invoke `product-impact`.

Trace the defect through user goal, friction, trust, conversion, support cost, operational risk, and recovery. Mark all unmeasured financial values as scenarios, not facts.

### 7. Select the next transition

Invoke `transition-next-action`.

Return the smallest justified action that preserves cooperation and evidence integrity. Do not jump from a public symptom directly to a remediation claim.

## Mandatory audit lenses

For a deep audit, cover all applicable lenses:

1. functional correctness;
2. state and temporal consistency;
3. UX, accessibility, and recovery;
4. content and semantic integrity;
5. performance and reliability;
6. privacy, authority, and security boundary;
7. causal validity and competing explanations;
8. product, conversion, and operational impact;
9. evidence freshness, replayability, and exact identity.

A lens can be `NOT_APPLICABLE`, but it cannot silently disappear.

## Output contract

Return these sections in order:

1. **Scope and authority**
2. **Executive verdict**
3. **Confirmed findings**
4. **Needs-evidence findings**
5. **Causal graph**
6. **Competing explanations and counterfactuals**
7. **User and business impact**
8. **Evidence ledger**
9. **Limitations and non-claims**
10. **Prioritized next actions**

Each finding must include:

- stable finding ID;
- claim level;
- severity and confidence;
- affected journey and profiles;
- observation trace IDs;
- causal parent and competing causes;
- reproduction status;
- freshness and exact source identity;
- user impact;
- business-impact status: measured, modeled, or unknown;
- next discriminating test;
- authority boundary.

## Fail-closed rules

- Search snippets, cached pages, and prior reports are discovery signals only.
- Source-only text does not prove visible impact.
- One browser profile does not prove cross-profile consistency.
- A successful HTTP response does not prove journey success.
- Correlation does not prove cause.
- Absence of an observed error does not prove absence of a defect.
- Unavailable evidence cannot be converted into approval.
- Prior memory cannot replace current reproduction.
- Automated review cannot grant ownership, remediation authority, external submission, deployment, or merge.
