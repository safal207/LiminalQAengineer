# OpenAI Public Web Benchmark v0.1

## Status

Configured for an exact-head GitHub Actions evidence run. Results are intentionally not pre-written: the benchmark must produce its own Lighthouse reports, decision packets, portfolio summary, and artifact digests.

## Purpose

This benchmark checks whether the existing LiminalQA public-web evidence pipeline transfers from trading platforms to a large AI platform ecosystem without weakening its safety or evidence boundaries.

The central cross-domain question is:

> Can LiminalQA produce bounded, reproducible quality evidence for public AI-platform surfaces using the same decision-packet contract used for public financial-platform surfaces?

## Exact public inventory

| Slug | Surface | Exact URL |
|---|---|---|
| `openai-home` | Company and product homepage | `https://openai.com/` |
| `chatgpt-public-shell` | Unauthenticated ChatGPT web entry | `https://chatgpt.com/` |
| `openai-codex` | Codex product overview | `https://openai.com/codex/` |
| `openai-developers` | Developer portal landing | `https://developers.openai.com/` |
| `openai-api-quickstart` | Public API quickstart documentation | `https://platform.openai.com/docs/quickstart/make-your-first-api-request` |
| `openai-help` | Help Center landing | `https://help.openai.com/en-us` |
| `openai-status` | Service status dashboard | `https://status.openai.com/` |

The inventory was verified against official OpenAI public surfaces on 2026-07-19.

## Safety boundary

The workflow performs exactly one passive Lighthouse navigation per allowlisted target, with at most two targets running concurrently.

It does **not**:

- authenticate or access a private workspace;
- submit prompts or create conversations;
- invoke models, APIs, tools, plugins, connectors, or agents;
- upload files or provide API keys;
- change an account, subscription, workspace, billing state, or settings;
- fuzz endpoints, bypass controls, perform load testing, or attempt exploitation;
- claim that a Lighthouse signal is a security vulnerability or proof of an outage.

Any future authenticated, API, adversarial, or security assessment requires a separate written scope and authorization. OpenAI's public disclosure policy remains the governing reference for any security-research path: <https://openai.com/policies/coordinated-vulnerability-disclosure-policy/>.

## Evidence contract

For each surface, the workflow stores:

1. the raw Lighthouse result;
2. the normalized LiminalQA decision packet;
3. the rendered human summary;
4. the exact raw-report SHA-256 digest;
5. runtime and Lighthouse version metadata;
6. category scores and thresholds;
7. Core Web Vitals and highest-priority scored findings.

The portfolio stage aggregates only domain packets produced by the same workflow run.

## Verdict semantics

- `PASS`: every audited category met the configured threshold.
- `WARN`: one or more quality categories fell below threshold.
- Workflow failure: evidence collection or validation did not complete; this is not converted into a product defect claim.

The benchmark does not use `FAIL` as a vulnerability label. A poor score is a bounded public-quality observation, not evidence of unauthorized access, unsafe model behavior, or service compromise.

## Interpretation rules

1. Compare surfaces before asserting a shared cause.
2. Separate public marketing, product shell, documentation, help, and status runtimes.
3. Treat redirects, bot protection, geolocation, consent surfaces, and transient incidents as possible confounders.
4. Do not infer model or API reliability from a static-page Lighthouse result.
5. Do not infer root cause from the Status page alone.
6. Preserve exact-head and artifact-digest provenance before publishing a causal conclusion.

## Expected next evidence step

After the first green exact-head run:

1. record the workflow run ID and exact head SHA;
2. download and hash the portfolio artifact;
3. classify shared versus surface-specific findings;
4. write an evidence-backed causality report;
5. propose at most one bounded browser-local counterfactual for the strongest supported web-performance cause.

No authenticated ChatGPT or API contract testing belongs in v0.1.
