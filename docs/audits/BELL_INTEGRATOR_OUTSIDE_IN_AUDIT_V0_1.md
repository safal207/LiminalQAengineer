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

The initial probe performs one sequential unauthenticated GET per route. It records final URL, HTTP status, response and visible-text SHA-256 values, bounded marker contexts, and the resulting tri-lens judgment.

## Initial claims under test

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

### BELL-003 · Career content has time and editorial debt

The careers page contains time-relative employee stories and editorial markers including:

- `не разу`;
- `за восемь с половиной лет` in a story that says the employee joined in 2011;
- `Мы предоставляет`;
- `вэб-сервиса`.

This is tested as a current employer-brand signal, not as proof of internal hiring-process quality.

### BELL-004 · Vacancy publishing exposes copy defects

Current engineering vacancy pages contain candidate-facing wording such as:

- `с огласованных лимитов`;
- `особенностей управление памятью`;
- `инстуменами отладки`.

The first audit treats these as editorial product signals. A systemic root-cause claim requires additional evidence.

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

The workflow produces:

```text
reports/bell-integrator/public-audit-v0.1/result.json
reports/bell-integrator/public-audit-v0.1/summary.md
reports/bell-integrator/public-audit-v0.1/exact-attempt.json
reports/bell-integrator/public-audit-v0.1/ARTIFACT_SHA256SUMS.txt
```

A later browser slice may add desktop/mobile screenshots, accessibility state, keyboard focus traces, console/network summaries, and rendered evidence hashes.

## Judgment limitations

- Public copy does not reveal the internal CMS, ownership model, or release process.
- Corporate metrics may use different business definitions; this must be reviewed before final severity.
- A visible typo does not by itself quantify candidate loss or sales conversion impact.
- External reporting remains blocked until a human reviews the evidence and decides whether collaboration outreach is appropriate.
