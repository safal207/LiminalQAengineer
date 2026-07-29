---
name: replay-memory
description: Store, retrieve, compare, and replay audit evidence using event-sourced and bi-temporal memory while preventing historical patterns from becoming decision authority. Use after evidence capture or when comparing a current finding with prior audits.
---

# Replay Memory

## Principle

Memory helps answer:

- Have we seen this pattern before?
- What evidence distinguished a real defect from noise?
- Did a prior fix survive over time?
- What did the auditor know at the decision moment?

Memory does not answer:

- Is the current system safe without a new check?
- Is this action authorized now?
- May the agent merge, deploy, disclose, or contact an external party?

## Event-sourced record

Store immutable events rather than rewriting the past:

```json
{
  "event_id": "AUDIT-EVENT-001",
  "audit_id": "AUDIT-001",
  "event_type": "observation|adjudication|reproduction|retraction|resolution",
  "valid_time": "RFC3339 timestamp",
  "transaction_time": "RFC3339 timestamp",
  "source_identity": {},
  "trace_refs": [],
  "evidence_refs": [],
  "claim_level": "OBSERVATION",
  "authority": "advisory_only"
}
```

Corrections append a new event that supersedes a prior interpretation. Raw evidence remains addressable.

## Retrieval procedure

1. Filter by target type, journey, finding code, environment, and time window.
2. Reject private, unauthorized, invalid, or incompatible records.
3. Prefer exact reproductions and resolved cases over textual similarity.
4. Return a small ranked set of analogues with their differences.
5. Label each result as `historical_context`, never `current_proof`.
6. Re-run the smallest discriminating check against current evidence.

## Replay procedure

Replay the ordered event trace against:

- the original source identity;
- the current source identity;
- the original environment assumptions;
- explicitly changed assumptions.

Report:

- same result;
- changed result;
- blocked replay;
- stale evidence;
- incompatible contract;
- missing artifact.

## Memory packet requirements

A reusable memory packet includes:

- stable finding and audit IDs;
- exact source identity;
- scope and authority;
- ordered trace;
- raw evidence hashes;
- adjudication history;
- competing explanations;
- discriminating test;
- resolution and regression status;
- valid-time and transaction-time fields;
- visibility classification.

## Safety rules

- No hidden memory count, path, or error may leak from a private store.
- Invalid or unauthorized memory is excluded without influencing the visible verdict.
- Similarity is not causality.
- A previously confirmed defect can be fixed; historical truth is not current truth.
- A previously safe state can regress; prior success is not current approval.
- Memory ranking must be deterministic for the same accepted packet set.
- The current evidence gate always outranks retrieved memory.

## Output

Return at most the most useful analogues, each with:

- why it matched;
- exact differences;
- prior claim level;
- prior resolution;
- whether replay succeeded;
- what must be checked now.
