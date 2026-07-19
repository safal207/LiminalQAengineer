# Tradernet public Lighthouse audit

## Purpose

This integration uses Lighthouse as a bounded public web-quality signal and converts the result into a LiminalQA decision packet.

```text
allowlisted public URL
→ one Lighthouse run
→ raw JSON/HTML evidence
→ category and metric extraction
→ LiminalQA PASS/WARN decision packet
```

The initial target is the public Tradernet website. This is a QA and usability audit, not a penetration test.

## Allowed targets

The single-page workflow currently permits these exact choices:

- `https://tradernet.ru/`
- `https://tradernet.ru/ideas/`
- `https://tradernet.ru/terminal`

The bounded portfolio workflow separately reads six exact targets from `audits/lighthouse/tradernet/domains.json`:

- `https://tradernet.ru/`
- `https://tradernet.com/`
- `https://rc.tradernet.com/faq/13096-how-to-open-an-account-as-an-individual?site_lang=en`
- `https://translate.tradernet.com/`
- `https://tradernet.global/`
- `https://tradernet.am/`

The single-page validator rejects query strings and fragments. The portfolio accepts a query string only when it is part of an exact inventory URL; arbitrary origins, credentials, ports, paths, fragments, and parameters remain outside scope.

## Safety boundary

The audit does not:

- authenticate;
- access portfolios or personal data;
- use API keys or secrets;
- submit orders or other financial operations;
- fuzz parameters;
- perform load testing;
- claim that a Lighthouse warning is a security vulnerability.

The workflow token has only `contents: read` permission.

## Run the workflow

Open **Actions → Tradernet Public Lighthouse Audit → Run workflow** and select one of the allowlisted URLs.

The job produces an artifact named `tradernet-lighthouse-<run id>` containing:

- Lighthouse raw JSON and HTML output;
- `decision-packet.json`;
- `summary.md`.

The Markdown summary is also written to the GitHub Actions job summary.

## Decision policy

| Category | Minimum score |
|---|---:|
| Performance | 65 |
| Accessibility | 85 |
| Best Practices | 85 |
| SEO | 85 |

A run is `PASS` when all four scores meet the policy. Otherwise it is `WARN`. A warning records quality debt but does not claim exploitation or block delivery automatically.

## Local conversion

After collecting a Lighthouse report in `.lighthouseci`:

```bash
python3 scripts/lighthouse_to_liminalqa.py report \
  --policy audits/lighthouse/tradernet/policy.json \
  --input-dir .lighthouseci \
  --output-dir reports/lighthouse
```

Validate a target before collection:

```bash
python3 scripts/lighthouse_to_liminalqa.py validate-url \
  --policy audits/lighthouse/tradernet/policy.json \
  --url https://tradernet.ru/
```

## Reporting boundary

A useful external report may describe measurable effects such as slow LCP, inaccessible controls, layout instability, or browser best-practice failures. It should not describe the result as a security bug unless a separate, authorized investigation establishes an actual security impact.
