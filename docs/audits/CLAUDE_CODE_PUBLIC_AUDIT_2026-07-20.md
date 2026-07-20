# Anthropic Claude Code public audit — 2026-07-20

## Executive verdict

Five official Claude Code product/documentation surfaces were observed in desktop and mobile profiles.

```text
execution: PASS
cells: 10/10
aggregate verdict: WARN
aggregate severity: HIGH
```

The strongest confirmed defect is a broken ARIA relationship on the public product page, reproduced in both profiles.

## Confirmed findings

### CLAUDE-A11Y-01 — tab controls reference nonexistent panels

Two visible product-page controls use `role="tab"` and `aria-controls`, but the referenced panel IDs are absent:

```text
Individual
aria-controls="_R_19iolubsnpfllb_-panel-0"

Onboarding
aria-controls="_R_bpkolubsnpfllb_-panel-0"
```

Lighthouse reports `aria-valid-attr-value` in desktop and mobile.

**Impact:** assistive technology receives a tab-to-panel relationship that cannot be resolved, weakening navigation and state understanding.

**Severity candidate:** P2/P3 accessibility, depending on screen-reader behavior in a manual matrix.

### CLAUDE-A11Y-02 — visible install command excluded from accessible name

On desktop, two install-command buttons visibly contain:

```text
curl -fsSL https://claude.ai/install.sh | bash
```

but expose only:

```text
aria-label="Copy command to clipboard"
```

Lighthouse reports `label-content-name-mismatch` because the visible command text is not included in the accessible name.

**Impact:** speech-input users may be unable to target the control using its visible content; screen-reader users do not receive the command represented by the control.

**Severity candidate:** P3 accessibility.

### CLAUDE-A11Y-03 — unnamed keyboard links on the product page

Desktop and mobile browser evidence each contain two enabled sequential `<a>` elements with no accessible name. The broad automated count is confirmed, but the final report should identify the business destination of each anchor before remediation ownership is assigned.

**Status:** confirmed public accessibility signal; exact link mapping required.

### CLAUDE-OBS-04 — event logging CORS failures

Both product profiles repeat six failed requests to:

```text
https://api.anthropic.com/api/event_logging/v2/batch
```

The browser reports a missing `Access-Control-Allow-Origin` response, producing 12 console errors per profile when paired with `net::ERR_FAILED`.

This is a reproducible technical integration failure, but no visible user journey failure was established. It is not treated as a product-blocking defect.

## Documentation performance signals

Claude Code docs show a large desktop/mobile gap in single-run laboratory data:

| Surface | Desktop performance | Mobile performance | Mobile LCP | Mobile TBT |
|---|---:|---:|---:|---:|
| Overview | 61 | 27 | 20.90 s | 3.38 s |
| Quickstart | 60 | 36 | 9.98 s | 3.94 s |
| CLI reference | 53 | 36 | 10.83 s | 3.09 s |

Unused JavaScript is reported in 8/10 cells, color contrast in 8/10, and bfcache/cache-lifetime signals recur broadly.

These values select the next experiment; they are not declared stable field regressions because only one Lighthouse run was used per cell.

## Other bounded signals

- `logoWall` is duplicated on the product page in both profiles.
- Documentation captures contain repeated IDs for context-menu, terminal, feedback, and assistant widgets. Hidden responsive duplication may explain some of them; manual accessibility impact must be established before promotion.
- Product performance scored `0`, but LCP/TBT were absent, making the category result incomplete rather than evidence that page rendering literally performs at zero.

## Rejected or bounded claims

- No account, installation, CLI, local file, repository, MCP, agent, or permission-mode execution occurred.
- No claim that Claude Code commands are unsafe or unavailable.
- No security-vulnerability claim.
- No performance severity based on one laboratory run.
- Analytics/event-logging failure is not equated with a failed user action.

## Exact evidence

```text
workflow run: 29769523371
attempt: 1
child PR: #94
child source head: b172a69a3d8e9ccdf9c6331aac361602ac17d142
aggregate artifact ID: 8472339939
aggregate artifact digest: sha256:0ce7eb564bd4fb6e9df8afd6b76c5ff4ef8cf030a1b9170a58689cd2e37cd469
result SHA-256: 6038103afada359adde3d4169ff640fd4cde233a5e6be7644db2b72e78e21e40
summary SHA-256: ae434f45520db2c61a1f98d84d81c82435d4471f5bce85bdaa3dc440e909b0db
evidence-index SHA-256: 00fde51010260bc88daf578838a1d7850890988beed814ef14fc3299cdf6317e
```

## Recommended fix order

1. Ensure every `aria-controls` value resolves to the active tabpanel ID in every responsive variant.
2. Include visible command text in the copy control's accessible name or separate the code and copy action semantically.
3. Give the two unnamed keyboard anchors stable accessible names.
4. Correct or remove the failing event-logging request configuration.
5. Run a three-sample mobile docs performance pass before setting performance severity.

## Authority

Evidence only. No ownership, approval, external submission, remediation assignment, deployment, or merge authority is granted.
