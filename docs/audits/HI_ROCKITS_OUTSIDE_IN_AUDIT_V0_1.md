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

The first exact run demonstrated why raw source and settled browser evidence are kept separate:

- KPI values `1740` and `72%` were present in the public response but not visible without opening a closed FAQ accordion;
- salary analytics pricing markers were reproducible through raw HTTP, while Chromium received HTTP `403` for that route;
- repeated testimonial and copy markers existed at source level, while the settled candidate UI displayed one testimonial and omitted the selected defects;
- the English page exposed several errors, but one desktop-only block made an over-broad combined assertion fail on mobile.

The contract therefore preserves the first three items as lower-level signals and narrows promotion to wording reproduced in both desktop and mobile.

## Findings

### ROCK-001 · KPI consistency — lower-level signal

The Russian public response contains different values for client count (`1742` and `1740`) and offer acceptance (`73%` and `72%`). The closed FAQ values were not visible in the passive settled UI, so this remains below confirmed-candidate level.

### ROCK-002 · Salary analytics monetary unit — lower-level signal

The raw salary analytics response presents prices such as `от 50 000 т.р.` and `от 530 000 т.р.`. In common Russian notation, `т.р.` means thousands of rubles, but Chromium received `403`; intended pricing and user-visible reproduction remain unconfirmed.

### ROCK-003 · Candidate source/UI divergence — needs evidence

The source-level candidate content includes duplicate and editorial signals. The settled desktop/mobile page showed only one tested testimonial and did not expose the selected copy markers. No user-visible defect is claimed from source alone.

### ROCK-004 · Russian proof-metric grammar

The buyer landing visibly publishes `4,76 процент замен кандидатов`. The value and unit label form an externally visible copy-quality signal.

### ROCK-005 · English editorial defects

The English acquisition page visibly contains:

- `Person behind CV is more important, than the text in it.`;
- `pervious stages`;
- `we werelooking for`.

### ROCK-006 · English language-mix residue

The Russian phrase `нужного специалиста` is embedded in the English workflow description.

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
- Hidden source content is not equivalent to a user-visible product defect.
- Business impact remains plausible but unmeasured.
