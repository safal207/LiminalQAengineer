# LiminalQA 1.0 Release Notes

**Release date**: Q1 2026
**Status**: Release candidate

---

## What is 1.0?

LiminalQA 1.0 is the first production-ready release of the quality intelligence
engine.  It covers the complete pipeline from raw test outcomes to actionable
quality decisions — without requiring manual triage, custom scripts, or
institutional memory about which failures are "known flakes".

---

## What's included in 1.0

### Core engine (`liminalqa-core`)

#### Decision layer
- `TestDecision` — structured judgment for one test: verdict, confidence,
  severity, recommended action, merge policy, retry policy, root cause hints
- `SuiteDecision` — aggregate judgment for a whole suite / PR; `merge_policy`
  is the worst-case across all constituent tests
- Closed-vocabulary `RecommendedAction` enum: `run`, `retry_immediately`,
  `retry_with_backoff`, `investigate`, `monitor_trend`, `skip`,
  `block_and_alert`, `observe_only`
- Fully serialisable to JSON — ready for GitHub Action bots, AI tool calling
  (Claude, GPT-4, Copilot), and CLI consumption

#### Triage engine
- Classifies each test as `stable` / `flake` / `new_bug` / `known_issue`
- Configurable stability threshold, run window, and minimum history
- Flake detection via oscillation scoring

#### EMA baselines + trend analysis
- `ExponentialBaseline` — online EMA (α = 2/(period+1)), tracks mean and
  standard deviation without storing full history
- Confidence score: grows 0 → 1 as samples accumulate
- Adaptive timeout: `EMA mean + k·σ` — zero config, self-calibrating
- `TrendStats` — linear regression on duration over time; detects degrading
  tests before they flake

#### Predictive flake risk
- `FlakeRiskScore` — combines triage verdict, oscillation, trend slope, and
  run stability into a single 0–100% probability
- Weighted logistic model; weights configurable per project

#### Retry policy
- `RetryPolicy` — derived from triage verdict + stability score
- Exponential backoff: initial delay, multiplier, max retries
- Smart selector: skip stable tests (≥97% pass rate, ≥10 runs); always run
  new and flaky tests

#### Context engine
- `SignalContext` — environment (prod/staging/dev) × time window
  (business hours/off-hours/night) × load level (low/normal/high)
- Context multiplier adjusts importance scores per observation

#### Causality + resonance
- Causality engine with time-decay: `strength = importance × exp(-Δt / 1000ms)`
- Multi-hop causality walks (A → B → C → D)
- Resonance map: test-to-signal correlation across time windows
- Flake detector: oscillation scoring, run-length analysis

#### Root-cause analysis (`rootcause`)
- 6 hypothesis kinds: `InfrastructureFlake`, `CodeRegression`,
  `TestDesignFlaw`, `ExternalDependency`, `ResourceExhaustion`,
  `EnvironmentConfig`
- Evidence-weighted scoring; confidence normalised across hypotheses
- Online Bayesian weight learning via `record_outcome` (learning rate 1/√n)
- Counterfactual reasoning: `what_if_fixed(result, kind)` returns predicted
  pass rate after the intervention

#### Knowledge sharing (`export` + `community`)
- `Anonymizer` — strips PII (IPs, URLs, paths) and hashes identifiers with a
  per-export salt; cross-export correlation impossible, intra-export stable
- `ExportBuilder` — produces versioned `PatternExportBundle` (schema 1.0)
  filtered by minimum run count, sorted by failure rate
- `PatternStore` — cosine-similarity nearest-neighbour search over 9-dim
  feature vectors; near-duplicate deduplication (sim ≥ 0.95)
- `generate_suggestions` — distils top-K matches into actionable advice
- `record_feedback` — Bayesian effectiveness update; surfaces what actually
  resolved the problem in other projects

#### Dashboard (`dashboard`)
- 4-panel text dashboard: Test Risk Card, Root Cause Analysis,
  What-if / Counterfactual, Community Insights
- 70-column terminal output — screenshottable, CI-log-friendly, pipe-friendly
- Zero external UI dependencies; renderable in any environment

### CI integrations

- **GitHub Actions** — workflow template: ingest results, status check,
  artifact upload
- **GitLab CI** — `.gitlab-ci.yml` template with MR comment support

---

## Key numbers

| Metric | Value |
|--------|-------|
| Test coverage | 79 unit tests, all passing |
| Build time (dev) | ~30s from scratch |
| Dashboard latency | <1ms (pure in-memory) |
| External runtime deps | 0 (embedded sled DB mode) |
| Lines of core logic | ~5 000 (excl. tests/docs) |

---

## What 1.0 is not

- **Not a test runner** — LiminalQA analyses test results; it does not replace
  pytest, cargo test, Jest, or your existing CI setup
- **Not a full UI product** — the dashboard is demo-grade terminal output;
  a web frontend is a post-1.0 item
- **Not a cloud service** — 1.0 ships as a library and CLI; hosted SaaS is
  a post-1.0 item
- **Not ML-heavy** — all models are interpretable (EMA, logistic weights,
  cosine similarity); no GPU required, no training pipeline

---

## Breaking changes from pre-1.0

This is the first stable release.  No compatibility guarantees were made
before 1.0.  Post-1.0 the public API (`TestDecision`, `SuiteDecision`,
`PatternExportBundle` JSON schemas) is stable under semver.

---

## Quick start

```bash
# Run the 3-scenario demo dashboard
cargo test -p liminalqa-core --test dashboard_demo -- --nocapture

# Run all tests
cargo test -p liminalqa-core

# Start the ingest service
cargo run --bin liminalqa-ingest

# CLI decision for a test
cargo run --bin limctl -- decision payments/charge_card
```

---

## Upgrade guide for pre-1.0 users

1. Update `liminalqa-core` to `0.1.0` (Cargo.toml)
2. Replace any direct `triage::classify()` calls with `DecisionEngine::evaluate_test()`
3. The `RecommendedAction` enum has two new variants: `BlockAndAlert` and
   `ObserveOnly` — add match arms if exhaustive matching
4. `SuiteDecision.merge_policy` now uses `MergePolicy::BlockSoft` (was missing
   before); update any match on `MergePolicy`

---

## What comes next (post-1.0 priorities)

| Priority | Item |
|----------|------|
| P1 | Web dashboard UI (React + Tailwind, consumes existing JSON API) |
| P1 | Case studies: 2–3 early adopter write-ups |
| P2 | PostgreSQL + pgvector backend for `PatternStore` |
| P2 | Community knowledge base (shared pattern server) |
| P3 | Seasonal decomposition in `ExponentialBaseline` |
| P3 | Changepoint detection (PELT algorithm) |
| P4 | LiminalOS hermetic runners |

---

## Acknowledgements

Built in Rust.  Dependencies kept minimal by design — sled, axum, tonic,
chrono, serde, sha2, prometheus-client.  No ML framework required.

*"Every quarter is a step from data to wisdom."*

— LiminalQA Roadmap, 2025
