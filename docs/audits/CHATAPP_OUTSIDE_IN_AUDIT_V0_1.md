# ChatApp outside-in audit v0.1

## Purpose

This document defines a bounded, independent audit of ChatApp's public unauthenticated web surfaces through three lenses:

- QA and content integrity;
- system and content-model consistency;
- business, buyer, developer, and partner-conversion impact.

The repository is the evidence and configuration center. The audit does not imply authorization to change ChatApp systems, activate controls, submit forms, access accounts, or contact the company.

## Scope

Canonical origin:

```text
https://chatapp.online
```

Allowlisted public routes:

- `/`;
- `/about/`;
- `/price/`;
- `/blog/new-price-2025/`;
- `/developers/`;
- `/developers/chatapp-developer/`.

The raw probe performs one sequential unauthenticated GET per route. The rendered probe observes every route in desktop and mobile Chromium profiles, without clicking controls.

## Claims under test

### CHAT-001 · Legal disclosure contains conflicting variants

The company page exposes both:

- `Общество с ограниченной ответственность «ЧатАпп»`;
- `Общество с ограниченной ответственностью «ЧатАпп»`.

The claim concerns visible public content quality. It does not assert that the legal entity itself is invalid.

### CHAT-002 · Expired pricing urgency remains published

The pricing article is dated `16 октября 2025`, but says:

- `С 1 мая 2025 года ... произойдет обновление тарифов`;
- `Только до 30 апреля 2025 года`;
- `Успейте продлить ChatApp`.

The audit checks whether the expired future-tense call to action remains visible alongside the current pricing surface.

### CHAT-003 · Two partner models share the Integrator label

The developer page presents two materially different journeys under the Integrator label:

- full client connection, support, and earnings;
- referral-only behavior where the integrator does not earn.

The claim is taxonomy ambiguity, not proof of a defective commercial contract.

### CHAT-004 · Commercial and developer pages contain language-quality defects

The initial bounded markers include:

- `управления взаимоотношения с клиентами`;
- `Как подключиться пример подключения через pusher.js`;
- `входящий/исходящий вэбхук`.

Only wording visible in settled desktop and mobile views can be promoted beyond `PRODUCT_SIGNAL`.

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

- authentication, registration, or account access;
- button or CTA activation;
- form submission, demo booking, checkout, or payment;
- direct application API testing;
- enumeration, fuzzing, load testing, or active security testing;
- vulnerability or legal-validity claims;
- email, telephone, social-media, or messenger contact;
- remediation, deployment, delivery, or merge.

## Expected artifacts

Raw evidence:

```text
reports/chatapp/public-audit-v0.1/result.json
reports/chatapp/public-audit-v0.1/summary.md
reports/chatapp/public-audit-v0.1/exact-attempt.json
reports/chatapp/public-audit-v0.1/ARTIFACT_SHA256SUMS.txt
```

Rendered evidence:

```text
reports/chatapp/rendered-audit-v0.2/chatapp-rendered-result.json
reports/chatapp/rendered-audit-v0.2/chatapp-rendered-summary.md
reports/chatapp/rendered-audit-v0.2/desktop-*.png
reports/chatapp/rendered-audit-v0.2/mobile-*.png
reports/chatapp/rendered-audit-v0.2/exact-attempt.json
reports/chatapp/rendered-audit-v0.2/ARTIFACT_SHA256SUMS.txt
```

## Judgment limitations

- Public copy does not reveal the internal CMS, ownership model, review process, or deployment pipeline.
- A dated article can be intentionally archived; severity depends on labeling, navigation context, and current buyer interpretation.
- Partner cards can rely on visual grouping that text extraction does not preserve; desktop/mobile screenshots require human review.
- Copy defects do not by themselves quantify lost leads, partner revenue, or conversion impact.
- External reporting remains blocked until a human reviews the exact artifacts and approves collaboration outreach.
