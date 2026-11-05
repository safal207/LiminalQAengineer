# LiminalQA company self-service public audit

This capability lets a company run a bounded public website quality and accessibility audit from its own GitHub repository while reusing the centrally maintained LiminalQA workflow and evidence engine.

The company keeps control of:

- the exact URLs under review;
- the caller repository and caller commit;
- the exact LiminalQA engine SHA or release tag;
- the schedule and optional quality gate;
- artifact retention.

The pipeline keeps the audit bounded and reproducible:

```text
company-owned JSON contract
→ fail-closed validation
→ target × desktop/mobile matrix
→ passive browser observation
→ keyboard/accessibility evidence
→ pinned Lighthouse runs
→ exact-attempt manifests
→ SHA-256 evidence index
→ aggregate PASS/WARN packet
```

## What it collects

For every configured target and browser profile:

- HTTP navigation status, final URL, and redirect chain;
- full-page screenshot;
- title, language, headings, landmarks, and structural counts;
- visible and sequentially focusable interactive controls;
- keyboard Tab trace and first-focus state;
- unnamed accessibility-tree controls;
- unnamed sequential controls;
- nested interactive controls;
- duplicate IDs, missing image alternatives, and unlabeled visible inputs;
- sanitized console signatures and failed-request metadata;
- navigation/resource timing totals;
- one to three pinned Lighthouse runs;
- category scores and core metrics;
- exact caller SHA, engine SHA, run ID, run attempt, config hash, and file hashes.

The aggregate artifact contains:

```text
company-audit-result.json
company-audit-summary.md
evidence-index.md
workflow-outputs.json
aggregate-exact-attempt.json
SHA256SUMS.txt
```

Each matrix-cell artifact also contains its browser result, screenshot, raw Lighthouse reports, summaries, exact-attempt manifest, and SHA-256 manifest.

## What it deliberately cannot do

The JSON schema contains no fields for:

- usernames, passwords, tokens, API keys, cookies, or custom headers;
- authentication or account access;
- custom JavaScript or browser-script injection;
- form submission, publishing, or state-changing actions;
- direct application API testing;
- orders, transfers, payments, or financial operations;
- fuzzing, enumeration, exploitation, or load testing;
- private, local, loopback, or custom-port targets.

Every contract must preserve the complete boundary block. Weakening or deleting one boundary causes validation to fail before browser execution.

This is a public quality and accessibility evidence workflow. It is not a penetration test, vulnerability report, legal/compliance certification, or substitute for manual assistive-technology testing.

## Option A — call the workflow from the company repository

Create a workflow such as `.github/workflows/public-quality-audit.yml`:

```yaml
name: Company Public Quality Audit

on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * 1"

permissions:
  contents: read

jobs:
  public-audit:
    uses: safal207/LiminalQAengineer/.github/workflows/company-public-audit.yml@PINNED_LIMINALQA_SHA
    with:
      config_path: .github/liminalqa/public-audit.json
      engine_ref: PINNED_LIMINALQA_SHA
      retention_days: 30
      fail_on: never
```

Use the same reviewed SHA or release tag for both:

- the reusable workflow reference after `@`;
- `engine_ref`.

This prevents the workflow definition and its scripts from silently coming from different revisions. A full example with outputs is stored at:

```text
docs/examples/company-audit-caller.yml
```

GitHub permits a repository to call a reusable workflow from a public repository when the caller's Actions policy allows public actions and reusable workflows. Pinning a commit SHA provides the strongest stability and supply-chain boundary.

## Option B — fork LiminalQAengineer

A company may also fork this repository, add its contract, and run:

```text
Actions
→ LiminalQA Company Public Audit
→ Run workflow
```

Provide:

- the committed config path;
- an exact engine SHA/tag or the reviewed fork branch;
- retention days;
- gate mode.

The workflow uses `workflow_dispatch` and the same evidence engine as external callers.

## Contract format

Start from:

```text
audits/templates/company-public-audit.example.json
```

Minimal example:

```json
{
  "schema_version": "liminalqa-company-public-audit-v1",
  "company": {
    "name": "Example Company",
    "audit_name": "Public website quality baseline"
  },
  "allowed_origins": [
    "https://www.example.com"
  ],
  "allowed_query_keys": [],
  "targets": [
    {
      "id": "home",
      "url": "https://www.example.com/",
      "kind": "marketing"
    }
  ],
  "profiles": [
    "desktop",
    "mobile"
  ],
  "settings": {
    "settle_ms": 3000,
    "keyboard_tab_steps": 20,
    "lighthouse_runs": 1,
    "max_parallel": 2,
    "retain_body_sample": false
  },
  "category_thresholds": {
    "performance": 0.65,
    "accessibility": 0.85,
    "best-practices": 0.85,
    "seo": 0.85
  },
  "boundaries": {
    "public_pages_only": true,
    "natural_navigation_only": true,
    "passive_browser_observation": true,
    "keyboard_navigation_only": true,
    "authenticated_testing": false,
    "account_access": false,
    "credentials_or_secrets": false,
    "direct_api_testing": false,
    "form_submission": false,
    "publishing": false,
    "financial_operations": false,
    "fuzzing": false,
    "load_testing": false,
    "active_security_testing": false,
    "server_state_change": false,
    "vulnerability_claim": false
  },
  "notes": []
}
```

### Origins and targets

- `allowed_origins` accepts 1–8 exact public HTTPS origins.
- Localhost, private/reserved IP addresses, credentials, and custom ports are rejected.
- `targets` accepts 1–8 pages.
- IDs must be lowercase slugs and unique.
- A target's origin must appear in `allowed_origins`.
- URL fragments are rejected.

### Query strings

Queries are rejected unless each query key is explicitly listed in `allowed_query_keys`.

Sensitive-looking keys such as `token`, `secret`, `auth`, `session`, `password`, `key`, `email`, `phone`, or `account` are rejected even when listed.

Example:

```json
{
  "allowed_query_keys": ["symbol"],
  "targets": [
    {
      "id": "btc-chart",
      "url": "https://charts.example.com/chart?symbol=BTCUSD",
      "kind": "chart"
    }
  ]
}
```

### Profiles

Supported profiles:

- `desktop`;
- `mobile`.

The matrix contains one evidence cell per target/profile combination.

### Settings

| Setting | Range | Meaning |
|---|---:|---|
| `settle_ms` | 0–15000 | Additional wait after DOMContentLoaded |
| `keyboard_tab_steps` | 0–40 | Passive Tab presses used for focus evidence |
| `lighthouse_runs` | 1–3 | Exact Lighthouse runs per cell; median scores are used |
| `max_parallel` | 1–4 | Maximum concurrent matrix jobs |
| `retain_body_sample` | boolean | Retain up to 2,000 public visible-text characters; default should remain false |

## Quality gate modes

`fail_on` controls whether evidence only warns or can fail the caller workflow:

| Value | Behavior |
|---|---|
| `never` | Always upload evidence; do not fail from quality signals |
| `high` | Fail only when aggregate severity is `HIGH` |
| `any-signal` | Fail whenever aggregate verdict is `WARN` |

The recommended onboarding mode is `never`. Review several runs before enabling a gate because public networks, regional variants, consent layers, and third-party resources can affect laboratory results.

## Reusable outputs

A caller receives:

- `verdict` — `PASS` or `WARN`;
- `severity` — `NONE`, `LOW`, `MEDIUM`, or `HIGH`;
- `artifact_name` — aggregate artifact name;
- `result_sha256` — SHA-256 of `company-audit-result.json`.

These outputs can feed a later company-owned approval or reporting job. LiminalQA itself does not merge, deploy, file an external ticket, or claim ownership of remediation.

## Decision boundary

The pipeline promotes only bounded automated signals:

```text
navigation failure or HTTP >= 400
→ HIGH quality warning

sequential focusables + zero Tab targets
→ keyboard focus warning

unnamed sequential/accessibility controls
or nested interactive controls
→ accessibility warning

Lighthouse median below configured threshold
→ Lighthouse quality warning
```

A workflow success state alone is never treated as evidence. Each conclusion is tied to exact result content, screenshots, raw reports, manifests, and hashes.

Automated warnings require human review before they are described as confirmed product defects. Root cause, user impact, severity, and remediation ownership remain human decisions.

## Versioning recommendation

Before external use:

1. review and merge the engine;
2. create a signed or protected release tag such as `company-audit-v1`;
3. publish the tag's commit SHA in this document;
4. have callers pin the SHA or tag in both workflow locations;
5. make incompatible schema changes under a new schema/workflow version.

## Files in this capability

```text
.github/workflows/company-public-audit.yml
.github/workflows/company-public-audit-engine-ci.yml
audits/templates/company-public-audit.example.json
scripts/company_public_audit_engine.py
scripts/company_public_browser_probe.mjs
tests/test_company_public_audit_engine.py
docs/examples/company-audit-caller.yml
docs/COMPANY_SELF_SERVICE_AUDIT.md
```
