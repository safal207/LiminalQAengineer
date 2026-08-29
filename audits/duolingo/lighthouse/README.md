# LiminalQA Lighthouse Adapter v0.3 — Duolingo

This package adds Lighthouse as an advisory sensor in the LiminalQA → GardenLiminal → LiminalDB → CML/LS/Lotus chain.

## Current run status

`DUO-LH-20260719-ENV-001` ended as `BLOCKED_BY_ENVIRONMENT` before target navigation. It produced zero valid Lighthouse Result (LHR) files, so it contains no Duolingo scores.

## Correct execution path

1. Use this package at `audits/duolingo/lighthouse/` in the LiminalQAengineer repository.
2. Open **Actions → Duolingo Lighthouse Manual Audit → Run workflow**.
3. Confirm the passive GET-only public audit.
4. Download the mobile and desktop evidence artifacts.
5. Feed `summary-*.json`, raw LHR files, environment identity and logs into CML and Lotus.

The root workflow `.github/workflows/duolingo-lighthouse-manual.yml` is `workflow_dispatch` only, has read-only repository permissions, executes profiles serially and preserves evidence when navigation fails.

## Decision boundary

A Lighthouse category score is not a final defect verdict. External Duolingo results may produce at most `WARN`; confirmation requires repeatability, raw LHR evidence, environment stability, a CML causal chain and LS user impact.
