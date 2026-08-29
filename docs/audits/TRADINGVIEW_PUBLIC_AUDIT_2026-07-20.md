# TradingView public audit — 2026-07-20

## Executive verdict

This is the first bounded TradingView public audit in the repository.

The six-route desktop/mobile matrix completed without anti-bot variants, and the public BTCUSD chart rendered successfully in both profiles.

The strongest new finding is an accessibility contract gap on the public chart:

```text
chart fully rendered
→ DOM contains sequential-focusable controls
→ 40 Tab presses produce zero focus targets
→ neutral click on empty chart area
→ another 40 Tab presses produce zero focus targets
```

The behavior reproduces in desktop and mobile profiles while TradingView's current accessibility statement says the chart supports Tab navigation across the top bar, drawings panel, right panel, and bottom panel.

Additional confirmed findings:

- active chart controls without accessible names;
- an interactive market-status button nested inside another button on the homepage in both profiles;
- a Google Identity/FedCM integration error in all 12 route/profile observations, with visible user impact not yet established.

A search/crawler hypothesis that the BTCUSD page simultaneously showed `Market closed`, `No trades`, and current market facts was **not reproduced** in the live browser and is rejected for reporting.

## Coordinate model

```text
O = official public TradingView URL
  + browser profile
  + viewport
  + unauthenticated state
  + observation time

N = passive unauthenticated browser
  and keyboard-only observer
```

Axes:

- `X` — route → visible market/community/chart component → interactive control;
- `Y` — loading → rendered → accessible → focused or unreachable;
- `Z` — desktop/mobile user-agent and viewport;
- `T` — navigation → settled render → Tab sequence → neutral chart activation → second Tab sequence.

## Scope

Twelve route/profile observations:

| Route | Desktop | Mobile |
|---|---:|---:|
| Homepage | HTTP 200 | HTTP 200 |
| BTCUSD symbol | HTTP 200 | HTTP 200 |
| BITSTAMP:BTCUSD public chart | HTTP 200 | HTTP 200 |
| BTCUSD ideas | HTTP 200 | HTTP 200 |
| Community scripts | HTTP 200 | HTTP 200 |
| Accessibility statement | HTTP 200 | HTTP 200 |

No anti-bot, CAPTCHA, access-denied, or mobile/desktop route divergence was observed.

## Finding TV-A11Y-CHART-01: chart keyboard navigation contract gap

**Severity candidate:** P2 accessibility  
**Confidence:** HIGH for the tested route and profiles

TradingView's accessibility statement says:

- chart interface elements can be navigated using the Tab key;
- the functionality covers the top bar, drawings panel, right panel, and bottom panel;
- visible focus states are prioritized.

### Desktop evidence

The public BITSTAMP:BTCUSD chart was visibly loaded:

- HTTP 200;
- 11 visible canvases;
- 109 visible SVGs;
- 81 visible interactive DOM elements;
- 79 enabled interactive elements;
- 12 elements with sequential focus eligibility.

Keyboard trajectory:

```text
40 × Tab before activation → 0 non-null focus steps → 0 unique targets
neutral click in empty chart area
40 × Tab after activation → 0 non-null focus steps → 0 unique targets
```

### Mobile evidence

The mobile chart was also visibly loaded:

- HTTP 200;
- 7 visible canvases;
- 41 visible SVGs;
- 39 visible interactive DOM elements;
- 37 enabled interactive elements;
- 1 element with sequential focus eligibility.

Keyboard trajectory:

```text
40 × Tab before activation → 0 focus targets
neutral click in empty chart area
40 × Tab after activation → 0 focus targets
```

No iframe boundary explains the observation: the inspected chart content and focusable elements were in the main frame.

### User impact

A keyboard-only user cannot reach the tested chart controls through the documented Tab navigation path, despite the chart being fully rendered and exposing interactive controls.

### Expected behavior

At minimum:

1. the first Tab should expose a visible focus target or chart-specific skip entry;
2. subsequent Tab/Shift+Tab should traverse the documented chart panels;
3. focus should remain visible and deterministic;
4. chart activation should not trap or suppress keyboard traversal.

## Finding TV-A11Y-NAME-02: enabled chart controls lack accessible names

**Severity candidate:** P2/P3 accessibility  
**Confidence:** HIGH

Concrete captured controls include:

### Desktop flag control

```html
<button type="button" ...>
  <span role="img" ... aria-hidden="true">...</span>
</button>
```

Observed properties:

- enabled;
- `tabIndex = 0`;
- no text;
- no `aria-label`;
- no title;
- the only icon is `aria-hidden`.

This creates an enabled sequential control with no accessible name.

### Main menu

Desktop and mobile both expose:

```html
<button data-qa-id="main-menu-button" aria-haspopup="menu" tabindex="-1">
  <svg>...</svg>
</button>
```

The button is enabled but has no accessible name and is excluded from the normal Tab order.

Desktop also contains an enabled dropdown icon control without an accessible name and with `tabindex=-1`.

The report does not promote the disabled unnamed Undo/Redo buttons because disabled controls have a different user-impact boundary.

## Finding TV-A11Y-STRUCTURE-03: nested market-status buttons

**Severity candidate:** P3 accessibility/markup  
**Confidence:** HIGH

The homepage reproduces the following structure in desktop and mobile:

```html
<button data-qa-id="symbol-overview-chart-header-market-status">
  <div>
    <button
      data-qa-id="legend-source-item-status"
      title="Market open"
      tabindex="0">
      ...
    </button>
  </div>
</button>
```

An interactive button is nested inside another interactive button. The outer button has no captured accessible name.

Potential effects include ambiguous screen-reader semantics, duplicate click targets, and inconsistent keyboard behavior. The structure is confirmed; a specific browser/screen-reader failure mode requires a dedicated assistive-technology matrix.

## Finding TV-IDENTITY-FEDCM-04: recurring public identity integration error

**Severity candidate:** P3 technical until visible impact is reproduced  
**Confidence:** HIGH for the console signature

All 12 route/profile observations produced the same public console error:

```text
FedCM get() rejects ... IdentityCredentialRequestOptions ...
mode 'widget' is not a valid enum value
```

The signature points to the Google One Tap / identity integration. It is a reproducible technical defect signal, but this audit did not attempt sign-in, so it does not claim that login is unavailable.

A focused next experiment should compare:

```text
One Tap eligible browser
→ prompt request
→ FedCM rejection
→ visible prompt/fallback state
→ manual sign-in entry availability
```

## Positive findings and rejected hypotheses

### Public chart loads successfully

The chart rendered in both profiles with visible candles, axes, watchlist, quote context, and multiple canvas/SVG surfaces.

### Website Skip Content works outside the full chart route

The homepage, BTC symbol, Ideas, Scripts, and accessibility statement exposed `Skip to main content` as the first keyboard focus target in both profiles.

The full chart route exposed no skip control and no Tab focus target in the tested trajectory.

### Market-state contradiction not reproduced

Live browser evidence on the BTCUSD symbol route showed:

```text
Market closed count: 0
No trades count: 0
```

in desktop and mobile. Therefore the crawler/search-text hypothesis is not included as a TradingView defect.

### Decorative links excluded from promoted finding

The broad DOM inventory found image-card anchors without names, but those anchors were `aria-hidden=true` and `tabindex=-1`. They are not used as proof of an accessibility failure in the final verdict.

### Third-party telemetry aborts rejected

Aborted Google Analytics/DoubleClick requests were observed, but no TradingView product failure is inferred from third-party telemetry aborts.

## Recommended fix order

1. Restore deterministic Tab traversal across the public chart and add a chart skip-entry or first-focus contract.
2. Give every enabled icon-only control an accessible name derived from its action/state.
3. Remove nested interactive button structures; use one button with one accessible name and state.
4. Update Google Identity integration to a supported FedCM mode and verify visible fallback behavior.
5. Add automated checks:
   - fresh chart load → first Tab target exists;
   - 20 Tab presses reach top/right/bottom/drawing panel controls;
   - zero enabled unnamed controls;
   - zero interactive descendants inside interactive ancestors;
   - zero FedCM enum errors on public entry routes.

## Evidence preservation

Canonical machine-readable report:

```text
audits/browser/tradingview/public-audit-result-2026-07-20.json
```

Evidence index:

```text
docs/audits/TRADINGVIEW_EVIDENCE_INDEX.md
```

Artifacts preserve:

- 12 full-page route/profile screenshots;
- the public-surface result and exact-attempt manifest;
- four keyboard trajectory screenshots;
- complete keyboard/focus JSON;
- accessibility statement text contexts;
- SHA-256 manifests.

## Safety and authority boundary

Only official public pages, natural navigation, Tab presses, and one neutral click in an empty chart coordinate were used.

No login, account access, direct API testing, forms, publishing, trading actions, financial operations, fuzzing, load testing, active security testing, or server-state change occurred.

The reports provide evidence and recommendations only. They grant no ownership, approval, execution, external submission, delivery, deployment, or merge authority.
