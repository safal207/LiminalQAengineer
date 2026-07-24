# Causal Deep-Audit Skills

This directory turns the Liminal portfolio into a reusable audit system instead of a collection of one-off prompts.

## Skill graph

```text
causal-deep-audit
  -> evidence-capture
  -> causal-adjudication
  -> exact-head-governance       (when a repository or PR is in scope)
  -> logo-fidelity-transfer      (when an approved brand reference must match a site)
  -> replay-memory
  -> product-impact
  -> transition-next-action
```

## Specialized skill

`logo-fidelity-transfer` binds an approved logo reference to canonical SVG geometry and browser-rendered selector captures. It uses Playwright for deterministic desktop/mobile evidence and Pixelmatch for expected/actual/diff artifacts, while preserving human brand approval and repository authority boundaries.

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
| `microsoft/playwright` | Browser engines, stable locator screenshots, viewport matrix, traces |
| `mapbox/pixelmatch` | Pixel-level expected/actual comparison and diff generation |

## Non-negotiable boundaries

1. Observation is not root cause.
2. A source marker is not automatically a rendered user-visible defect.
3. Missing evidence is `NEEDS_EVIDENCE`, `NOT_RUN`, or `INCOMPLETE`; it is never success.
4. Memory can suggest a prior pattern but cannot authorize a verdict.
5. Automated output is advisory-only unless an explicitly separate enforcement system is in scope.
6. Public-surface audits remain passive and bounded unless the owner has explicitly authorized a broader test.
7. Commercial impact is a model or hypothesis until measured.
8. Pixel similarity cannot grant trademark, design, deployment, or merge approval.

## Canonical result states

- `NOT_RUN`
- `NEEDS_EVIDENCE`
- `PRODUCT_SIGNAL`
- `CONFIRMED_PRODUCT_DEFECT_CANDIDATE`
- `CONFIRMED_DEFECT`
- `BLOCKED_BY_BOUNDARY`
- `INCOMPLETE`
- `HOLD`
- `READY_WITH_ADVISORY_GAPS`

The orchestrator must preserve the strongest applicable uncertainty state rather than compressing it into a green/red summary.
