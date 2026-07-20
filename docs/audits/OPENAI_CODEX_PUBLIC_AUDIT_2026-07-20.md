# OpenAI Codex public audit — 2026-07-20

## Executive verdict

A bounded public desktop/mobile audit covered five official Codex product and documentation surfaces.

```text
execution: PASS
cells: 10/10
aggregate verdict: WARN
aggregate severity: MEDIUM
```

No account, ChatGPT login, repository connection, model request, Codex task, CLI execution, installation, form submission, direct API call, or security test was performed.

## Strong confirmed public findings

### OAI-CODEX-A11Y-01 — Codex pet control label mismatch

The docs overview exposes a draggable Codex pet button whose visible text is `1/8`, while its accessible name is:

```text
Show next Codex pet. Codey is selected.
```

Lighthouse reports `label-content-name-mismatch`: the visible label is not included in the accessible name. The element is a real keyboard button, not decorative content.

**Impact:** voice-control and speech-input users cannot reliably activate the control using the text they see.

**Severity candidate:** P3 accessibility.

### OAI-CODEX-A11Y-02 — invalid heading progression in Codex Security docs

The main Security article contains:

```html
<h3 id="explore-plugin-use-cases">Explore plugin use cases</h3>
```

without an intervening article-level `h2`. Lighthouse reproduces `heading-order` in desktop and mobile evidence.

**Impact:** screen-reader heading navigation communicates an inconsistent document outline.

**Severity candidate:** P3 accessibility/document structure.

### OAI-CODEX-A11Y-03 — recurring docs contrast and link-text signals

Across the documentation portfolio:

- `color-contrast` appears on five route/profile cells;
- CLI docs report three links without sufficiently descriptive text in both profiles;
- the docs overview repeats a control label/content mismatch;
- accessibility scores remain high overall, so these are localized defects rather than a claim that the docs are broadly inaccessible.

Final severity requires reviewing the exact affected nodes and design tokens.

## Delivery candidate — not promoted as a confirmed product defect

The Codex product page produced a sharp profile split on the same GitHub-hosted environment.

### Desktop profile

```text
HTTP: 200
visible h1: This page couldn’t load
body text length: 68
focus targets: Reload, Back
console errors: 20
first-party static chunk failures: HTTP 403 / MIME errors
```

### Mobile profile

```text
HTTP: 200
full Codex marketing page rendered
70 sequential-focusable elements
30 unique Tab targets observed
```

This is retained as:

```text
UA_OR_CDN_DEPENDENT_DELIVERY_CANDIDATE
```

It is **not** promoted because the probe pins a Chrome 126 user-agent while the hosted runner uses a newer Chrome build, the mobile profile rendered successfully, and a separate normal public fetch also reached the page. A native-UA versus pinned-UA counterfactual is required before attributing the failure to OpenAI.

The same caution applies to the product/get-started mobile performance values from a single laboratory run.

## Portfolio results

| Surface | Desktop P/A/BP/SEO | Mobile P/A/BP/SEO | Interpretation |
|---|---|---|---|
| Product | 92 / 97 / 59 / 100 | 32 / 100 / 61 / 100 | desktop rendered fallback; mobile performance directional only |
| Get started | 90 / 97 / 59 / 100 | 37 / 100 / 61 / 100 | large JS payload and deprecated APIs; one run |
| Docs overview | 92 / 96 / 78 / 100 | 73 / 96 / 79 / 100 | localized a11y and image-delivery signals |
| CLI docs | 99 / 96 / 78 / 92 | 83 / 97 / 79 / 92 | contrast and non-descriptive link text |
| Security docs | 98 / 94 / 78 / 100 | 71 / 99 / 79 / 100 | heading-order defect; mobile LCP directional |

Scores are triage signals, not field percentiles or root-cause proof.

## Rejected or bounded claims

- No claim that Codex itself, ChatGPT, the CLI, or repository tasks are unavailable.
- No security-vulnerability claim.
- No stable performance regression claim from one Lighthouse run.
- No assumption that every console/DevTools issue is user-visible.
- No product attribution for the desktop fallback until the UA/CDN counterfactual is complete.

## Exact evidence

```text
workflow run: 29769492765
attempt: 1
child PR: #93
child source head: 6b82f5c6a8b1a38d4c19986d14c16d15dcd29189
aggregate artifact ID: 8472386423
aggregate artifact digest: sha256:e0e9d750ea9c1a2abbfdc1313d19c420a3775475306a809eb19d4c7acd6b2805
result SHA-256: a503e1582d76db97db0990183c27b2ef5ca665808d395871346bc3e363b4efff
summary SHA-256: 899c289b65fb7e4e24351d608c8f6e150cb7c7ed845e6a5edea4dc2f13471782
evidence-index SHA-256: 8ca96bf14cfc2bb3b2bfc411f760f07a78e005e4cf6b001ac3d36053b3a5b7d5
```

## Recommended next experiments

1. Native browser UA versus pinned Chrome 126 UA on `/codex/` and `/codex/get-started/`.
2. Repeat each performance route three times before discussing regression or severity.
3. Add automated checks for heading order, descriptive link text, contrast, and visible-label inclusion.
4. Verify the Codex pet control with voice control and a screen reader.

## Authority

Evidence only. No ownership, approval, external submission, remediation assignment, deployment, or merge authority is granted.
