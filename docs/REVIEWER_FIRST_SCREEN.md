# Reviewer First Screen

Status: shortest entry point for grant, fellowship, and external reviewers.

## One sentence

LiminalQAengineer is a causality-aware QA/CI reliability substrate for turning raw test outcomes into reproducible quality decisions.

## Core thesis

```text
CI failure -> causal signals -> decision packet -> merge/retry/block recommendation
```

LiminalQAengineer helps teams understand whether a failing test is likely a real bug, flake, infrastructure issue, known issue, or stable regression signal.

## Review in five minutes

1. Read `README.md`.
2. Read `AI_SAFETY_PORTFOLIO.md`.
3. Run the Docker quickstart from `docs/MVP1_QUICKSTART.md` if you want to inspect the full QA/CI pipeline.
4. Review the bi-temporal data model and causality walk examples.

## What LiminalQAengineer is

LiminalQAengineer is an open-source reliability engineering project. It applies causal and bi-temporal reasoning to CI/test workflows.

It currently focuses on:

- structured test outcome analysis;
- flake interpretation;
- root-cause-oriented QA reports;
- bi-temporal quality facts;
- reproducible run/test/signal data;
- decision packets for merge, retry, warn, or block.

## What LiminalQAengineer is not

LiminalQAengineer is not:

- the main AI safety product in the portfolio;
- a full AI alignment system;
- a production security certification tool;
- a compliance product;
- a replacement for human QA judgment;
- a universal prevention system for software failures.

## Best current funding framing

```text
Fund LiminalQAengineer as open-source QA/CI reliability infrastructure that supports causal failure analysis and reproducible quality decisions.
```

Near-term work:

- harden the ingest/report path;
- improve reproducible demos;
- clarify the bi-temporal model;
- expand flake and root-cause examples;
- connect the reliability layer with the broader AI-agent evidence-gate portfolio.

## Bottom line

LiminalQAengineer makes one missing layer inspectable:

```text
Why did this test/workflow fail, and what should the team do next?
```
