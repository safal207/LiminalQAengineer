# AI Safety Portfolio Map

Status: reviewer-facing map for grant, fellowship, and collaboration reviewers.

This file explains how LiminalQAengineer fits into the broader AI safety and agent-oversight portfolio.

## One-line research program

Deterministic evidence, intent, and causal accountability layers for high-risk AI-agent actions before they create real-world effects.

## LiminalQAengineer in the portfolio

### LiminalQAengineer

**Role:** QA reliability substrate.

LiminalQAengineer applies causal and bi-temporal reasoning to CI and test workflows. It helps teams move from simple pass/fail test output toward reproducible root-cause understanding, flake interpretation, and quality decision packets.

It is not the main AI safety object in the portfolio. It supports the engineering reliability foundation behind the safety work.

Best reviewer framing:

```text
LiminalQAengineer is a causality-aware QA/CI reliability substrate that demonstrates the maintainer's practical background in reproducible failure analysis and quality decision systems.
```

## Related layers

### PythiaLabs

**Role:** pre-execution evidence gates.

PythiaLabs evaluates whether a proposed high-risk AI-agent action has enough evidence, authorization, context, and recovery viability to proceed.

```text
AI agent proposes action -> evidence gate -> ALLOW / BLOCK / ESCALATE
```

PythiaLabs is the cleanest grant-facing entry point for AI safety and agent oversight reviewers.

### ProofPath

**Role:** verifiable intent and action-boundary audit.

ProofPath focuses on whether a critical action is causally authorized and auditable at the execution boundary.

```text
valid credential != valid action != valid scope != valid reversibility != valid approval
```

### CML — Causal Memory Layer

**Role:** causal permission and responsibility lineage.

CML records not only what happened, but why an action was allowed, blocked, or escalated. It is the causal accountability layer behind oversight decisions.

### LTP — Liminal Thread Protocol

**Role:** trace, replay, and admissibility path.

LTP structures multi-step agent traces so that decisions can be replayed, compared, and audited across sessions.

## Recommended reviewer paths

### For open-source infrastructure reviewers

1. Start with `README.md`.
2. Run the Docker quickstart if you want to inspect the QA/CI pipeline.
3. Review the bi-temporal data model and causality walk examples.
4. Treat this repository as reliability infrastructure, not the central AI safety product.

### For AI safety reviewers

1. Use LiminalQAengineer as evidence of practical failure-analysis experience.
2. Review PythiaLabs for the main pre-execution action-gate work.
3. Review ProofPath for execution-boundary intent and audit patterns.

## What this repository is not

LiminalQAengineer does not claim:

- full AI alignment;
- complete agent safety;
- production security certification;
- regulatory compliance;
- replacement of human review;
- universal prevention of unsafe actions.

Its contribution is narrower:

```text
make QA/CI failures more causal, reproducible, and decision-ready.
```

## Bottom line

The broader portfolio should be read as a layered safety stack:

```text
PythiaLabs -> evidence gate
ProofPath -> intent and audit boundary
CML -> causal accountability
LTP -> trace and replay protocol
LiminalQAengineer -> reliability substrate
```

The shared thesis:

```text
AI-agent actions and software quality decisions should be reviewable, replayable, and evidence-backed before they cause downstream harm.
```
