# Hi, Rockits! outside-in audit v0.1

## Purpose

This document defines a bounded, independent audit of the public unauthenticated Hi, Rockits! web surfaces through three lenses:

- QA and content integrity;
- system and content-model consistency;
- business, buyer, and candidate-conversion impact.

The repository is the evidence and configuration center. The audit does not authorize contact, form submission, resume upload, remediation, deployment, or merge.

## Scope

Official origins:

```text
https://rockits.ru
https://hirockits.com
```

Allowlisted routes:

```text
https://rockits.ru/
https://rockits.ru/candidate
https://rockits.ru/it-salary-analytics
https://hirockits.com/
```

The raw probe performs one sequential unauthenticated GET per route. The rendered slice observes each route in desktop and mobile Chromium, captures full-page screenshots, visible-text hashes, bounded console/network summaries, structure metrics, and keyboard Tab traces.

## Claims under test

### ROCK-001 · KPI consistency

The Russian home page presents different values for client count (`1742` and `1740`) and offer acceptance (`73%` and `72%`). The audit treats this as a content-governance signal, not proof that either value is false.

### ROCK-002 · Salary analytics monetary unit

The salary analytics page presents prices such as `от 50 000 т.р.` and `от 530 000 т.р.`. In common Russian notation, `т.р.` means thousands of rubles, so the displayed unit may multiply the intended amount by 1,000. Final judgment requires company context about the intended amount and suffix.

### ROCK-003 · Candidate journey quality

The candidate page appears to repeat the same testimonial block and contains visible editorial signals including `Инфрастуктура` and concatenated words in a testimonial. The browser layer must distinguish source duplication from actual rendered duplication.

### ROCK-004 · English localization quality

The English acquisition page contains grammatical errors, concatenated words, a wrong word (`pervious`), and a Russian phrase. The browser layer must confirm that every marker is visible.

## Evidence ladder

```text
search result or cached snippet
→ NEEDS_EVIDENCE

marker reproduced in a current public response
→ PRODUCT_SIGNAL

same issue reproduced in settled desktop and mobile renders
→ CONFIRMED_PRODUCT_DEFECT_CANDIDATE

human semantic and impact review
→ final severity and collaboration decision
```

## Authority boundary

The audit explicitly does **not** authorize:

- authentication;
- form submission or contact requests;
- resume upload;
- button or CTA activation;
- direct API testing;
- enumeration, fuzzing, or load testing;
- active security testing or vulnerability claims;
- publication or external reporting;
- remediation, deployment, delivery, or merge.

## Expected artifacts

Raw:

```text
reports/hi-rockits/public-audit-v0.1/result.json
reports/hi-rockits/public-audit-v0.1/summary.md
reports/hi-rockits/public-audit-v0.1/exact-attempt.json
reports/hi-rockits/public-audit-v0.1/ARTIFACT_SHA256SUMS.txt
```

Rendered:

```text
reports/hi-rockits/rendered-audit-v0.2/hi-rockits-rendered-result.json
reports/hi-rockits/rendered-audit-v0.2/hi-rockits-rendered-summary.md
reports/hi-rockits/rendered-audit-v0.2/*.png
reports/hi-rockits/rendered-audit-v0.2/exact-attempt.json
reports/hi-rockits/rendered-audit-v0.2/ARTIFACT_SHA256SUMS.txt
```

## Judgment limitations

- Public copy does not reveal internal CMS ownership or release processes.
- Different KPI values may refer to different time windows or definitions.
- The intended price unit cannot be inferred conclusively without company context.
- Testimonial text may be a verbatim customer quote; the audit only assesses the published candidate journey.
- Business impact remains plausible but unmeasured.
