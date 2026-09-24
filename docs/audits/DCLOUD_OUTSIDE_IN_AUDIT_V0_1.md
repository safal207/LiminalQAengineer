# DCloud Outside-In Audit v0.1

## Purpose

Use `safal207/LiminalQAengineer` as the evidence and configuration center for an independent DCloud public audit across three lenses:

1. **QA engineer** — reproducibility, content integrity, route behavior, accessibility, and browser quality;
2. **system analyst** — shared source-of-truth, content lifecycle, state transitions, ownership, and control gaps;
3. **business analyst** — candidate/client conversion, trust, lost-contact risk, international positioning, and remediation priority.

This is an evidence-only outside-in review. It is not commissioned penetration testing and does not authorize external reporting.

## Exact base

The branch starts from `main` SHA:

```text
d1caf64db824aeb6486d1e741b999f74533e29b7
```

## Coordinate model

```text
O = official public URL + unauthenticated state + observation time
N = passive external observer
X = domain -> route -> content block -> claim
Y = current -> ambiguous -> contradictory -> stale/template
Z = raw public response -> rendered desktop/mobile confirmation
T = navigation -> settled response -> normalization -> human judgment
```

## First bounded portfolio

The machine-readable contract allowlists only selected HTTPS pages on `https://dcloud.tech`:

- Russian commercial landing;
- current Russian contacts;
- legacy contact page `page14540121.html`;
- legacy/team template page `page16808528.html`;
- QA vacancy;
- Russian company profile;
- English commercial landing.

The probe runs sequentially with a response-size limit and blocks redirects outside the canonical origin.

## Initial claims under test

### DCL-001 · Unfinished team template

The canonical domain exposes a page containing unrelated Finnish travel copy, Badoo team text, repeated placeholder employees, and template vacancies.

- QA lens: public release/content-integrity signal;
- system lens: stale-page retirement and publication-inventory gap;
- business lens: trust loss for a candidate or client arriving through search or an old link.

### DCL-002 · Conflicting contact identity

A legacy page exposes `info@dcloud.ru`, `www.dcloud.app`, an older phone/address set, and a `2014–2022` copyright, while the current contacts surface uses `hr@dcloud.tech` and `© 2025 DCloud`.

- QA lens: contradictory public state;
- system lens: duplicated contact identity without one governed source;
- business lens: lost lead, misrouted resume, or abandonment.

### DCL-003 · Mixed QA vacancy model

The QA vacancy combines an “8-hour working week” phrase, full-time/hourly conditions, developer-style live refactoring/live coding, and text offering work to junior/middle developers.

- QA lens: inconsistent or role-incongruent content;
- system lens: vacancy-template leakage across disciplines;
- business lens: lower conversion of qualified QA candidates.

### DCL-004 · Reused role descriptions

Several specialist roles reuse the Backend/Fullstack Team Lead description.

- QA lens: label/description mismatch;
- system lens: missing typed content constraints and duplication checks;
- business lens: weaker proof of multidisciplinary capability.

### DCL-005 · English localization quality

The English storefront contains repeated markers such as `Our personality`, `come driven professionals`, `Focus on outome`, and `Microservice Personality`.

- QA lens: grammar, spelling, and semantic quality signals;
- system lens: missing editorial acceptance and language-parity gates;
- business lens: reduced international credibility.

## Evidence ladder

```text
search/index observation
        -> NEEDS_EVIDENCE
public response marker reproduced
        -> PRODUCT_SIGNAL
settled desktop + mobile rendered reproduction
        -> CONFIRMED_PRODUCT_DEFECT_CANDIDATE
human semantic and impact review
        -> final severity / report decision
```

A marker match is not a root-cause proof. A low Lighthouse score is not a defect by itself. A security claim is blocked unless separately authorized, scoped, and supported by demonstrated security impact.

## Current workflow

`.github/workflows/dcloud-outside-in-audit-v0-1.yml`:

1. validates the contract and authority boundaries;
2. compiles the probe and runs regression tests;
3. performs one sequential passive GET per allowlisted target;
4. normalizes the public response;
5. evaluates evidence assertions;
6. builds QA/system/business finding packets;
7. uploads exact-attempt JSON and Markdown evidence.

## Next experiment

Add a browser-level desktop/mobile adapter that captures:

- final URL and HTTP/navigation state;
- screenshot;
- visible text evidence;
- internal/external links relevant to each claim;
- accessibility tree and keyboard trace;
- console and failed-request summaries;
- content and screenshot SHA-256.

Only after that run may a reproduced raw-response signal be promoted toward a confirmed visible defect.

## Safety and authority

No authentication, form submission, email, Telegram contact, direct application API calls, enumeration, fuzzing, load testing, active security testing, external report, deployment, or merge is performed or authorized.

The repository stores evidence and judgment inputs. It does not own DCloud remediation decisions and it does not contact the company automatically.
