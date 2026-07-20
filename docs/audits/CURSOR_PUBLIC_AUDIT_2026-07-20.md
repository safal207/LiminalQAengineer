# Cursor public audit — 2026-07-20

## Executive verdict

Five official Cursor product, pricing, security, onboarding, and CLI routes were tested in desktop and mobile profiles.

```text
execution: PASS
cells: 10/10
aggregate verdict: WARN
aggregate severity: HIGH
```

The strongest confirmed defects are focusable content inside `aria-hidden` demo windows and degradation of historical deep documentation links to the generic docs home.

## Confirmed findings

### CURSOR-A11Y-01 — `aria-hidden` demo windows contain keyboard-focusable controls

The public home page marks several large interactive demo containers as hidden from assistive technology:

```html
<div aria-hidden="true" id="demo-window-cursor-ide">...</div>
<div aria-hidden="true" id="demo-window-cursor-agent-cli">...</div>
<div aria-hidden="true" id="demo-window-agent-react-hooks">...</div>
<div aria-hidden="true" id="demo-window-slack">...</div>
<div aria-hidden="true" id="demo-window-automation-config">...</div>
```

Yet their descendants remain focusable, including:

- `Get Cursor`, `Open settings`, model and Build buttons;
- `Get CLI` and an `Add a follow-up` text input;
- Slack channel controls;
- automation switches and configuration buttons.

Lighthouse reproduces `aria-hidden-focus` in desktop and mobile.

**Impact:** keyboard focus can enter content that screen readers are instructed not to expose, producing silent or disorienting focus transitions.

**Severity candidate:** P2 accessibility.

### CURSOR-DOCS-02 — deep documentation links lose their destination

Both tested historical documentation routes redirect to the generic docs root:

```text
https://docs.cursor.com/en/get-started/quickstart
→ https://cursor.com/docs

https://docs.cursor.com/en/cli/overview
→ https://cursor.com/docs
```

The behavior reproduces in desktop and mobile.

**Impact:** bookmarks, search results, external tutorials, and internal links no longer land on the requested Quickstart or CLI content. The user must rediscover the destination manually.

**Severity candidate:** P2/P3 documentation routing, depending on inbound traffic and availability of replacement deep links.

### CURSOR-A11Y-03 — docs home exposes unnamed/nested interactive controls

After the deep-link redirect, desktop evidence on the generic docs page contains:

- an enabled `role="button"`, `tabindex=0`, with no accessible name;
- an enabled `role="separator"`, `tabindex=0`, with no accessible name;
- one unnamed accessibility-tree control;
- a disabled submit button without an accessible name;
- a heading-anchor whose visible text `Start here` is not included in its accessible name `Copy link to start-here`.

The DOM observer also records one nested-interactive structure around the docs sidebar toggle. The stored parent descriptor is generic, so remediation should confirm the exact ancestor semantics before classifying it as invalid HTML.

**Severity candidate:** P3 accessibility; unnamed focusable controls should be fixed first.

### CURSOR-A11Y-04 — recurring contrast failures

`color-contrast` appears in all 10 cells. On the home page examples include muted gray and orange text below the required contrast threshold. This is repeated across desktop and mobile, not a single-route anomaly.

**Severity candidate:** P2/P3 depending on affected text role and font size.

## Technical signals with bounded impact

- The docs page attempts a browser Summarizer API request with unsupported language options and logs an error. The effect on the visible docs journey was not established.
- Console errors occur across all 10 cells, but several are WebGL/experimental browser-service signals; they are not automatically promoted.
- The home page contains duplicate IDs in responsive demo content. Exact assistive-technology impact needs manual confirmation.

## Directional performance signals

| Surface | Desktop performance | Mobile performance | Interpretation |
|---|---:|---:|---|
| Home | 79 | 30 | heavy JS/DOM; one run |
| Pricing | 90 | 44 | directional only |
| Security | 94 | 31 | directional only |
| Quickstart redirect target | 73 | 27 | generic docs home measured |
| CLI redirect target | 64 | 27 | generic docs home measured |

Because the two docs routes redirect to the same generic destination, their performance data must not be described as CLI- or Quickstart-specific performance.

## Rejected or bounded claims

- No download, installer, login, subscription, model request, indexing, agent, Bugbot, or cloud-agent action occurred.
- No security-vulnerability claim.
- Missing-alt DOM counts on home were not promoted because Lighthouse image-alt passed; these are likely decorative/observer-overcount cases.
- Analytics, WebGL, and browser experimental-service errors are not treated as user-visible defects without a causal journey.
- One Lighthouse run is not a stable field-performance regression.

## Exact evidence

```text
workflow run: 29769555934
attempt: 1
child PR: #95
child source head: 591d68a5f878a94336a98633c189432cf875f590
aggregate artifact ID: 8472361710
aggregate artifact digest: sha256:2828eb70e2fe7b5ced2f9ef4250ed67f31a39d940b0b6d3edbea4ad056ebb492
result SHA-256: 9ea8033eabb499ada7b8c63d42f4ded6f57fe71506ba79bbe8ea47d10b644dd9
summary SHA-256: fec6d0169af3df35888532f8252ce9224307672a07487acedf3f0229d9784030
evidence-index SHA-256: 16f2848d1ce8edf9024e8e01cab0ff7364b6cddbdc60119d50db03f0c160c1fd
```

## Recommended fix order

1. Remove focusability from `aria-hidden` demo descendants, or expose the active demo with correct semantics and hide only inactive copies.
2. Preserve old Quickstart/CLI deep links with route-specific redirects to replacement pages.
3. Name every focusable docs control and correct the heading-link accessible-name mismatch.
4. Fix recurring contrast tokens across marketing, pricing, security, and docs surfaces.
5. Repeat mobile performance measurements after the routing and accessibility fixes.

## Authority

Evidence only. No ownership, approval, external submission, remediation assignment, deployment, or merge authority is granted.
