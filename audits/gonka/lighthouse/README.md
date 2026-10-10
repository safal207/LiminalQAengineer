# LiminalQA Lighthouse Adapter v0.1 — Gonka

This package audits only Gonka's public website and documentation routes. It does not connect wallets, sign or submit transactions, generate API keys, send inference requests, operate nodes, mine, fuzz APIs, or submit reports to HackerOne.

## Target identity

- Protocol repository: `gonka-ai/gonka`
- Protocol head at audit creation: `8a35022bea25ebee4b7356314a0a262edbaa82db`
- Documentation repository: `gonka-ai/gonka-docs`
- Documentation head at audit creation: `902f9074b70cbdbcbf9343bc0e22a153503b87aa`

## Chain

```text
Pythia preflight
→ GitHub-hosted isolated Lighthouse runner
→ raw LHR + environment evidence
→ LiminalDB evidence lineage
→ CML product/environment causality
→ LS user-control impact
→ Lotus review
→ LiminalQA Decision Packet
```

## Routes

- `https://gonka.ai/`
- `https://gonka.ai/docs/`
- `https://gonka.ai/docs/developer/quickstart/`
- `https://gonka.ai/docs/host/quickstart/`
- `https://gonka.ai/docs/report-vulnerability/`

## Run modes

- Pull request: one smoke run per URL for mobile and desktop.
- Manual workflow: three runs per URL for repeatability and median analysis.

## Decision boundary

Lighthouse is an advisory sensor. A score alone is not a defect. Product confirmation requires repeated raw evidence and user impact. Security reports must go through Gonka's official HackerOne program and may not be submitted automatically by this adapter.
