# Gonka Lighthouse Decision Packet

**GitHub Actions run:** `29684917873`  
**Audit adapter head:** `bc24e50c8d0690077e5a588ba26755095b1ee266`  
**Protocol head:** `8a35022bea25ebee4b7356314a0a262edbaa82db`  
**Documentation head:** `902f9074b70cbdbcbf9343bc0e22a153503b87aa`  
**Environment:** Ubuntu 24 runner, Chrome `150.0.7871.114`, LHCI `0.15.1`, Lighthouse `12.6.1`  
**Evidence:** 10 valid LHR reports — five mobile and five desktop  
**Lotus verdict:** `WARN`

## Scores

Values are **Performance / Accessibility / Best Practices / SEO**.

| Route | Mobile | Desktop |
|---|---:|---:|
| `/` | 69 / 79 / 96 / 83 | 95 / 79 / 96 / 83 |
| `/docs/` | 92 / 89 / 96 / 83 | 98 / 89 / 96 / 83 |
| `/docs/developer/quickstart/` | 74 / 90 / 96 / 92 | 98 / 90 / 96 / 92 |
| `/docs/host/quickstart/` | 55 / 90 / 89 / 83 | 92 / 90 / 93 / 83 |
| `/docs/report-vulnerability/` | 71 / 93 / 75 / 92 | 96 / 93 / 74 / 92 |

## Repeated product signals

### GONKA-A11Y-001 — HackerOne report iframe has no accessible title

The official vulnerability-reporting page embeds the HackerOne submission form in an iframe without a `title`. The same failure appears in mobile and desktop LHRs.

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P2  
**Impact hypothesis:** screen-reader users are not told the purpose of the embedded frame on the security reporting path. Manual screen-reader confirmation is still required.

### GONKA-A11Y-002 — Documentation search dialog has no accessible name

The MkDocs search component uses `role="dialog"` without an accessible name on the documentation landing page, developer quickstart, host quickstart, and vulnerability-reporting page. The failure repeats in both profiles.

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P2

### GONKA-A11Y-003 — Technical documentation has repeated contrast and link-distinguishability failures

- Developer quickstart: 41 contrast nodes and 10 links that rely on color alone in both profiles.
- Host quickstart: 80 contrast nodes and 30 links that rely on color alone in both profiles.
- The affected content includes environment variables, shell commands, internal anchors, and operational guidance.

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P2

### GONKA-WEB-004 — Home and documentation landing pages have no document title

The home page and `/docs/` fail the Lighthouse `document-title` audit in both mobile and desktop profiles.

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P3

### GONKA-I18N-005 — Invalid relative hreflang URLs across every tested route

Every tested page exposes English and Chinese `hreflang` links using relative `href` values. Lighthouse rejects these as invalid in both profiles.

Examples include:

```html
<link rel="alternate" hreflang="en" href="./">
<link rel="alternate" hreflang="zh" href="../../zh/host/quickstart/">
```

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P3

### GONKA-WEB-006 — Page-relative sitemap requests return 404

All tested routes log failed sitemap requests. Nested pages request paths such as:

```text
/docs/developer/quickstart/sitemap.xml
/docs/zh/developer/quickstart/sitemap.xml
/docs/host/quickstart/sitemap.xml
/docs/zh/host/quickstart/sitemap.xml
```

The home page also requests `/zh/sitemap.xml`. These requests return 404 in both profiles.

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P3

### GONKA-WEB-007 — Landing page emits repeatable runtime exceptions

The public landing page logs the same runtime errors in both profiles:

```text
ReferenceError: document$ is not defined
ReferenceError: Missing element: expected "[data-md-component=header]" to be present
```

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P3  
**Boundary:** visible functional impact has not yet been manually reproduced.

### GONKA-A11Y-008 — Landing-page navigation has unnamed links and small touch targets

The landing page has unnamed logo/social links in both profiles, six insufficient touch targets, repeated contrast failures, and a skipped heading level.

**Classification:** `PRODUCT_SIGNAL`  
**Priority:** P3

## Performance boundary

The host quickstart produced mobile LCP `9.34s` and TBT `777ms`, while desktop produced LCP `1.76s` and TBT `16ms`. The vulnerability-reporting page produced mobile LCP `5.16s`, while desktop produced `0.81s`.

This pass collected one run per URL per profile. Performance therefore remains `NEEDS_EVIDENCE`; the values may include device emulation, CDN, third-party HackerOne resources, and runner variance. A manual three-run pass is required before a performance defect is confirmed.

## Security boundary

No wallet connection, signing, transaction, inference, node operation, mining, fuzzing, enumeration, port scanning, or load testing was performed. No security vulnerability was confirmed. The missing iframe title is a product accessibility signal, not a HackerOne submission by itself.

## Lotus decision

```yaml
execution: PASS
raw_lhr_count: 10
accessibility_and_web_structure: PRODUCT_SIGNAL
performance: NEEDS_EVIDENCE
security_vulnerability: NOT_CONFIRMED
hackerone_submission: NOT_AUTHORIZED_BY_EVIDENCE
external_target_maximum: WARN
overall_decision: WARN
next_action:
  - run_three_pass_manual_evidence
  - verify_keyboard_navigation
  - verify_screen_reader_on_hackerone_iframe
  - verify_visible_impact_of_home_runtime_exceptions
```
