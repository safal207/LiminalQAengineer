# Bell Integrator outside-in audit v0.1

## Purpose

This document defines a bounded, independent audit of Bell Integrator's public unauthenticated web surfaces through three lenses:

- QA and content integrity;
- system and content-model consistency;
- business and candidate-conversion impact.

The repository is the evidence and configuration center. The audit does not imply authorization to change Bell Integrator systems or contact the company.

## Scope

Canonical origin:

```text
https://bellintegrator.ru
```

Allowlisted public routes:

- `/`;
- `/company`;
- `/information/careers`;
- `/node/12`;
- `/vacancy/2495`;
- `/vacancy/2496`.

The raw probe performs one sequential unauthenticated GET per route. The rendered probe observes each route in desktop and mobile profiles. Together they record final URL, HTTP status, visible text, bounded marker contexts, accessibility state, console/network summaries, screenshots, and SHA-256 integrity values.

## Claims under test

### BELL-001 · QA service copy maps to ABS modernization

The home page publishes the same banking-system modernization paragraph for both `Развитие АБС` and `Комплексные услуги по обеспечению качества (QA)`. The QA detail route `/node/12` also exposes the ABS modernization paragraph.

- QA lens: unrelated copy is attached to a core service.
- System lens: service type, card copy, and detail copy are not protected by a typed content contract.
- Business lens: the QA storefront itself can weaken trust in Bell Integrator's release discipline.

### BELL-002 · Corporate facts are not governed consistently

The current domain contains these public claims:

- home/careers: `7` offices or representative offices;
- company page: `девять представительств`;
- home/careers: fixed `20 years` metric;
- company page: operating since `2003`.

In July 2026, a fixed 20-year metric does not align with a 2003 start date. Final judgment must still distinguish offices from representative offices and confirm whether the difference is intentional.

### BELL-003 · Visible grammar defect on the careers page

The rendered careers page exposes the phrase:

```text
Мы предоставляет полный набор услуг
```

This is treated as a candidate-facing editorial defect, not as proof of internal hiring-process quality.

### BELL-004 · Vacancy publishing exposes visible copy defects

The rendered engineering vacancies expose candidate-facing wording including:

- mixed Cyrillic/Latin script in `QА`;
- `особенностей управление памятью`;
- `инстуменами отладки`.

These are treated as editorial product signals. A systemic root-cause claim requires additional evidence.

## Source-to-rendered adjudication

The first raw pass also observed older employee-story text and a split `с огласованных` sequence in source-derived text. Browser evidence changed the judgment:

- the older employee stories were present in the document source but were not visible in settled desktop or mobile `innerText`;
- the browser rendered `согласованных` as one normal word, so the raw spacing marker was a parser-boundary artifact rather than a user-visible defect;
- visible defects such as `Мы предоставляет`, mixed-script `QА`, and the iOS vacancy wording remained reproducible.

The contract was therefore narrowed to user-visible evidence instead of promoting hidden or parser-created signals.

## Evidence ladder

```text
search result or cached snippet
→ NEEDS_EVIDENCE

marker reproduced in current public response
→ PRODUCT_SIGNAL

same issue reproduced in settled desktop and mobile renders
→ CONFIRMED_PRODUCT_DEFECT_CANDIDATE

human semantic and impact review
→ final severity and collaboration decision
```

## Authority boundary

The audit explicitly does **not** authorize:

- authentication or account access;
- form submission;
- email, telephone, social-media, or messenger contact;
- direct application API testing;
- enumeration, fuzzing, or load testing;
- active security testing or vulnerability claims;
- remediation, deployment, delivery, or merge.

## Expected artifacts

Raw evidence:

```text
reports/bell-integrator/public-audit-v0.1/result.json
reports/bell-integrator/public-audit-v0.1/summary.md
reports/bell-integrator/public-audit-v0.1/exact-attempt.json
reports/bell-integrator/public-audit-v0.1/ARTIFACT_SHA256SUMS.txt
```

Rendered evidence:

```text
reports/bell-integrator/rendered-v0.2/bell-integrator-rendered-result.json
reports/bell-integrator/rendered-v0.2/bell-integrator-rendered-summary.md
reports/bell-integrator/rendered-v0.2/desktop-*.png
reports/bell-integrator/rendered-v0.2/mobile-*.png
reports/bell-integrator/rendered-v0.2/exact-attempt.json
reports/bell-integrator/rendered-v0.2/ARTIFACT_SHA256SUMS.txt
```

## Judgment limitations

- Public copy does not reveal the internal CMS, ownership model, or release process.
- Corporate metrics may use different business definitions; this must be reviewed before final severity.
- A visible typo does not by itself quantify candidate loss or sales conversion impact.
- Accessibility and runtime observations are supporting signals unless promoted through a separate bounded finding contract.
- External reporting remains blocked until a human reviews the evidence and decides whether collaboration outreach is appropriate.
