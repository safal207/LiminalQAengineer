# Causal Deep-Audit Skills

This directory turns the Liminal portfolio into a reusable audit system instead of a collection of one-off prompts.

## Skill graph

```text
causal-deep-audit
  -> evidence-capture
  -> causal-adjudication
  -> cyber-causal-audit           (when security is explicitly in scope)
      -> websocket-redis-lifecycle
         (for WebSocket, Redis, Pub/Sub, reconnect, heartbeat and cleanup)
  -> exact-head-governance        (when a repository or PR is in scope)
  -> replay-memory
  -> product-impact
  -> transition-next-action
```

## Security route

`cyber-causal-audit` adds a repository-grounded security path:

```text
authority and exact scope
-> external-skill source, license and permission gate
-> threat model and trust boundaries
-> assets, identities, owners and invariants
-> static, differential and variant review
-> smallest safe discriminating test
-> false-positive gate
-> exact-head evidence
-> human severity and disclosure decision
```

External methods are pinned in `cyber-causal-audit/sources.json`. The default adoption mode is inspiration or reference only. Third-party prompts, scripts, hooks, plugins and rules are not executed merely because their repository or model vendor is well known.

`websocket-redis-lifecycle` specializes the security route for:

- identity-domain mismatches such as `user_id`, `ws_id`, session and generation;
- subscribe/unsubscribe and increment/decrement symmetry;
- reconnect generation fencing;
- multi-socket cleanup;
- Redis Pub/Sub self-echo and duplicate delivery;
- heartbeat, crash and zombie cleanup;
- snapshot versus incremental semantics;
- temporal field integrity and provenance.

## Repository responsibilities

| Repository / protocol | Responsibility in an audit |
| --- | --- |
| `LiminalQAengineer` | Orchestration, bounded probes, evidence packets, reproducible reports |
| `T-Trace` | Ordered event and observation trace |
| `Causal-Memory-Layer` | Causal lineage, missing-parent and ambiguous-root checks |
| `pythiaLabs` | Deterministic evidence gate: allow, block, or escalate |
| `LS` | Exact-head identity, frozen evidence, fail-closed PR scorecard |
| `LiminalDB` | Event-sourced replay and durable memory without decision authority |
| `transition-intelligence-protocol` | Checked readiness and the smallest justified next transition |
| `LiminalOSAI` / Lotus principles | Advisory synthesis, human authorship, no authority escalation |

## Non-negotiable boundaries

1. Observation is not root cause.
2. A source marker is not automatically a rendered user-visible defect.
3. A suspicious code pattern is not automatically reachable or exploitable.
4. An analog repository cannot prove another product uses the same internal implementation.
5. Missing evidence is `NEEDS_EVIDENCE`, `NOT_RUN`, or `INCOMPLETE`; it is never success.
6. Memory can suggest a prior pattern but cannot authorize a verdict.
7. Automated output is advisory-only unless an explicitly separate enforcement system is in scope.
8. Public-surface audits remain passive and bounded unless the owner has explicitly authorized a broader test.
9. External skills remain untrusted until exact source, license, scripts, prompts, hooks, dependencies and permissions are reviewed.
10. Commercial impact is a model or hypothesis until measured.
11. Audit output does not authorize credentials, exploitation, production stress, disclosure, remediation, deployment or merge.

## Canonical result states

- `NOT_RUN`
- `NEEDS_EVIDENCE`
- `PRODUCT_SIGNAL`
- `SECURITY_SIGNAL`
- `DEFECT_CANDIDATE`
- `VULNERABILITY_CANDIDATE`
- `RESOURCE_LEAK_CANDIDATE`
- `CONFIRMED_PRODUCT_DEFECT_CANDIDATE`
- `CONFIRMED_DEFECT`
- `CONFIRMED_VULNERABILITY`
- `BLOCKED_BY_BOUNDARY`
- `INCOMPLETE`
- `HOLD`
- `READY_WITH_ADVISORY_GAPS`

The orchestrator must preserve the strongest applicable uncertainty state rather than compressing it into a green/red summary.