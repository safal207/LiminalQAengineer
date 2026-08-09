# NLnet Commons Fund reviewer path — 2026-06-0c5

Status: grant-specific reviewer entry point.

Project: **LiminalQAengineer: Open Causality and Temporal Memory for QA Pipelines**

Application code: **2026-06-0c5**  
Call: **Commons Fund**  
Requested amount: **€50,000**  
Planned duration: **6 months**

This document maps the claims and work packages in the submitted NLnet proposal to the current public repository. It deliberately separates **what already exists** from **what the grant is intended to harden or extend**.

## One-sentence application claim

LiminalQAengineer is open-source QA infrastructure for turning fragmented CI/test evidence into reproducible, causality-oriented quality analysis while preserving quality facts on two time axes: `valid_time` and `tx_time`.

## Review in five minutes

1. Read this file.
2. Run the decision-packet demo:

```bash
cargo test -p liminalqa-core --test dashboard_demo -- --nocapture
```

3. Inspect the general evidence package: [`GRANT_EVIDENCE.md`](GRANT_EVIDENCE.md).
4. Inspect the bi-temporal implementation paths:
   - `liminalqa-core/src/temporal.rs`
   - `liminalqa-db/src/index.rs`
   - `liminalqa-db/src/query.rs`
   - `liminalqa-db/src/storage.rs`
   - `services/liminal-db/migrations/`
5. Inspect the causality path:
   - `liminalqa-core/src/causality/`
   - `liminalqa-core/src/rootcause.rs`
   - `services/liminal-report/`
6. Inspect the ingest / runnable path:
   - `liminalqa-ingest/`
   - `limctl/`
   - [`MVP1_QUICKSTART.md`](MVP1_QUICKSTART.md)
   - `scripts/demo.sh`
7. Run the broader test suite if desired:

```bash
cargo test
```

## Submitted work packages

The application requested six months of solo-maintainer work across three packages:

| Work package | Submitted scope | Current baseline in this repository | Grant-funded hardening / next evidence |
| --- | --- | --- | --- |
| **WP1 — months 1–2** | Stabilize ingest/run/report path and publish reproducible demo | Rust ingest, runner/CLI paths, report components, Docker/MVP quickstart, decision-packet demo and demo script are present | Make one canonical end-to-end reviewer fixture deterministic across clean environments; tighten failure diagnostics; publish reproducibility evidence for the full ingest → analysis → report path |
| **WP2 — months 3–4** | Improve temporal query/causality workflows and flake interpretation | Bi-temporal types/storage/query paths exist; causality/root-cause modules exist; flake/regression decision framing and demo are present | Add benchmark fixtures and acceptance tests for temporal queries, causal trails and flake interpretation; make uncertainty/evidence inputs explicit; test behavior across heterogeneous CI histories |
| **WP3 — months 5–6** | Security/CI hardening and operator documentation | CI/security workflows, Docker paths, monitoring docs, architecture docs and operator-oriented quickstarts exist | Harden reproducibility/supply-chain controls, expand CI integration examples, formalize operator runbooks and produce grant-period validation artifacts tied to exact revisions |

The grant is therefore not framed as funding a greenfield repository. It funds the transition from a broad working prototype into a reproducible, reviewer-verifiable open QA reliability substrate.

## Application claim → repository evidence

| Proposal claim | Current evidence | Boundary / non-claim |
| --- | --- | --- |
| Multi-source structured run/test/signal ingestion | `liminalqa-ingest/`, README ingest endpoints, MVP quickstart | Current repo demonstrates an ingestion architecture; it does not claim universal adapters for every CI provider |
| Bi-temporal quality facts using `valid_time` and `tx_time` | `liminalqa-core/src/temporal.rs`, `liminalqa-db/src/index.rs`, `query.rs`, `storage.rs`, DB migrations | Presence of the model is not the same as proving correctness for all temporal workloads; WP2 should add benchmark/acceptance evidence |
| Causality-oriented reflection rather than pass/fail-only output | `liminalqa-core/src/causality/`, `rootcause.rs`, `services/liminal-report/`, dashboard demo | Root-cause output is a structured hypothesis/decision aid, not guaranteed causal truth |
| Flake interpretation | core decision/triage code, dashboard demo, flaky-CI case study | No claim of universal statistical calibration across every language/framework |
| Self-hosted / on-prem path | Dockerfile, compose files, MVP quickstart | This is an operator path, not a production certification |
| Reproducible QA decisions | decision packet demo, JSON/report structures, tests and CI | Grant work should strengthen exact-revision evidence and deterministic end-to-end fixtures |
| Open implementation without vendor lock-in | public repository, MIT license | No claim that LiminalQA replaces CI systems, QA engineers or observability platforms |

## Current architecture relevant to the application

```text
CI / test signals
      ↓
structured ingest
      ↓
run + test + signal facts
      ↓
bi-temporal storage
(valid_time × tx_time)
      ↓
triage / flake / causality analysis
      ↓
reflection + decision packet
      ↓
human / CI bot / coding-agent action
```

The repository currently exposes this through modular Rust components including:

- `liminalqa-core`
- `liminalqa-db`
- `liminalqa-runner`
- `liminalqa-ingest`
- `limctl`

## Reviewer evidence map

| Reviewer question | Evidence path |
| --- | --- |
| Can I see an actionable decision rather than raw pass/fail? | `cargo test -p liminalqa-core --test dashboard_demo -- --nocapture` |
| Is the temporal model implemented in code? | `liminalqa-core/src/temporal.rs`, `liminalqa-db/src/` |
| Is causal analysis more than a README claim? | `liminalqa-core/src/causality/`, `liminalqa-core/src/rootcause.rs` |
| Is there an ingest path for external run/test/signal data? | `liminalqa-ingest/`, README API section |
| Can the stack be run by a reviewer? | `docs/MVP1_QUICKSTART.md`, Docker/compose paths, `scripts/demo.sh` |
| Are limits and uncertainty stated? | `docs/GRANT_EVIDENCE.md` → “What this project does not claim yet” |
| Is there operational/security hardening? | `.github/workflows/`, `docs/monitoring/`, `docs/audits/` |

## Evidence snapshot at reviewer-path creation

Reviewer-path baseline revision:

```text
c811fff33515c8d5a75d4f67a40ee8b337a083c5
```

At packaging time, the scheduled **Security Audit** workflow on `main` completed successfully for this revision on 2026-08-09 (run #544).

This SHA is an evidence snapshot, not a promise that reviewers must use an old revision. Reviewers should normally inspect the current `main` and use the SHA only to understand what evidence was present when this mapping was created.

## Acceptance criteria for the grant-funded delta

The strongest interpretation of the submitted work packages is that a reviewer should be able to verify the following without relying on private demonstrations:

### WP1 acceptance

- one documented command path exercises ingest → stored facts → analysis → report;
- fixture inputs are committed and reproducible;
- expected outputs or invariant checks are versioned;
- failures produce actionable diagnostics rather than silent partial success.

### WP2 acceptance

- temporal queries are covered by deterministic tests over `valid_time` and `tx_time`;
- causal/reflection output links conclusions to the evidence used;
- flake/regression fixtures cover positive, negative and ambiguous cases;
- uncertainty is exposed rather than converted into false certainty.

### WP3 acceptance

- core CI/security checks run from clean environments;
- operator instructions reproduce the supported path;
- validation artifacts identify the exact source revision they came from;
- supported deployment claims are explicitly separated from unimplemented or experimental paths.

## Explicit non-claims

For grant review, the project should **not** be read as claiming:

- perfect or scientifically proven root-cause identification;
- universal flake detection;
- replacement of human QA judgment;
- automatic safe merging without policy controls;
- production security certification;
- compatibility with every CI provider;
- that every roadmap item is already implemented.

The narrower claim is the useful one:

> LiminalQAengineer provides an open, inspectable substrate for preserving QA evidence over time and turning CI/test signals into structured causal hypotheses and quality decisions.

## Related reviewer documents

- [`GRANT_EVIDENCE.md`](GRANT_EVIDENCE.md) — general evidence package
- [`REVIEWER_FIRST_SCREEN.md`](REVIEWER_FIRST_SCREEN.md) — shortest general reviewer entry point
- [`MVP1_QUICKSTART.md`](MVP1_QUICKSTART.md) — runnable stack path
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — architecture
- `case-studies/` — concrete QA decision scenarios
- `monitoring/` — operational monitoring material

## Bottom line

The application asked NLnet to fund hardening of three linked capabilities:

```text
reproducible QA ingestion
        +
bi-temporal quality memory
        +
causality-oriented interpretation
        ↓
inspectable quality decisions
```

The repository already contains a substantial baseline for all three. The grant-specific task is to make that baseline deterministic, benchmarked, operationally hardened and easy for an external reviewer to reproduce.