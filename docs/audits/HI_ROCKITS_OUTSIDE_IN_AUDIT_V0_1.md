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

## Source-to-rendered adjudication

The exact runs demonstrated why raw source and settled browser evidence are kept separate:

- KPI values `1740` and `72%` were present in the public response but not visible without opening a closed FAQ accordion;
- the salary analytics route initially returned Chromium `403`, then reproduced its price labels in the final exact run on both desktop and mobile;
- repeated testimonial and copy markers existed at source level, while the settled candidate UI displayed one tested testimonial and omitted the selected defects;
- the original English assertion was too broad because one block was desktop-only, so it was split into wording reproduced in both profiles.

The final contract therefore confirms four user-visible candidates and preserves two lower-level signals.

## Confirmed rendered candidates

### ROCK-002 · Salary analytics monetary unit

The salary analytics page visibly presents prices such as `от 50 000 т.р.`, `от 530 000 т.р.`, and `от 690 000 т.р.` in desktop and mobile.

In common Russian notation, `т.р.` denotes thousands of rubles. The display therefore appears to scale the intended amounts by 1,000, although the intended commercial price must be confirmed with Hi, Rockits! before any final severity or loss claim.

### ROCK-004 · Russian proof-metric grammar

The buyer landing visibly publishes `4,76 процент замен кандидатов` in desktop and mobile. The metric value and unit label form an externally visible copy-quality signal.

### ROCK-005 · English editorial defects

The English acquisition page visibly contains in both profiles:

- `Person behind CV is more important, than the text in it.`;
- `pervious stages`;
- `we werelooking for`.

### ROCK-006 · English language-mix residue

The Russian phrase `нужного специалиста` is embedded in the English workflow description in desktop and mobile.

## Lower-level signals

### ROCK-001 · KPI consistency — needs rendered evidence

The Russian public response contains different values for client count (`1742` and `1740`) and offer acceptance (`73%` and `72%`). The closed FAQ values were not visible in the passive settled UI, so this remains below confirmed-candidate level.

### ROCK-003 · Candidate source/UI divergence — needs evidence

The source-level candidate content includes duplicate and editorial signals. The settled desktop/mobile page showed only one tested testimonial and did not expose the selected copy markers. No user-visible defect is claimed from source alone.

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
- The intended salary-analytics price cannot be inferred conclusively without company context.
- Hidden source content is not equivalent to a user-visible product defect.
- Business impact remains plausible but unmeasured.
