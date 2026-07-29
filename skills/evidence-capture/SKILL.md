---
name: evidence-capture
description: Capture bounded, reproducible evidence for websites, applications, APIs, repositories, and user journeys. Use before declaring a product defect, causal claim, or business impact.
---

# Evidence Capture

## Objective

Turn a possible problem into an ordered, replayable evidence package without crossing the declared authority boundary.

## Boundary first

Record:

- target allowlist;
- public, authenticated, repository, or PR scope;
- allowed methods and prohibited actions;
- exact source SHA or public response marker;
- time, locale, device, viewport, browser, account state, and network conditions;
- stop conditions.

For a public outside-in audit, default to passive sequential navigation only. Do not authenticate, submit forms, enumerate, fuzz, load test, probe private APIs, change server state, or make vulnerability claims without explicit authorization.

## Evidence ladder

```text
search or prior report
-> DISCOVERY_SIGNAL

current source response
-> PRODUCT_SIGNAL

settled rendered reproduction
-> CONFIRMED_PRODUCT_DEFECT_CANDIDATE

code/state-transition evidence plus human adjudication
-> CONFIRMED_DEFECT
```

Never skip a rung by rhetoric.

## Capture matrix

For every affected journey, collect the applicable rows:

| Layer | Minimum evidence |
| --- | --- |
| Source | URL/path, status, content hash or source SHA, relevant excerpt |
| Rendered UI | desktop and mobile settled screenshots, visible text, layout state |
| Interaction | keyboard trace, focus order, touch target, reachable controls, recovery path |
| Runtime | console summary, failed requests, redirects, final origin, loading state |
| Accessibility | name/role/state, contrast or structure signal, keyboard operability |
| Temporal | timestamps, state before/after refresh, Back/Forward, retry, reconnect |
| Cross-context | locale, account, viewport, device, or second-session comparison |
| Repository | exact head, changed files, checks actually run, unavailable checks |

## T-Trace event shape

Each observation should be representable as:

```json
{
  "trace_id": "TRACE-001",
  "sequence": 1,
  "observed_at": "RFC3339 timestamp",
  "actor": "human|browser|probe|ci|reviewer",
  "action": "navigate|render|inspect|refresh|compare|run_check",
  "target": "bounded target",
  "pre_state": {},
  "post_state": {},
  "evidence_refs": [],
  "result": "observed|not_observed|blocked|not_run",
  "notes": "facts only"
}
```

## Source-to-rendered adjudication

Source markers can be hidden, normalized, corrected by CSS/DOM behavior, or split across parser boundaries. Before calling a user-visible defect:

1. wait for a defined settled state;
2. inspect visible text or accessibility state, not source alone;
3. reproduce in the declared profiles;
4. record whether the marker survives navigation and refresh;
5. reject parser artifacts and hidden legacy content from the confirmed set.

## Reproduction packet

Every candidate finding needs:

- preconditions;
- numbered steps;
- expected result;
- actual result;
- frequency;
- first and last observed timestamps;
- affected profiles;
- raw evidence references;
- cleanup or recovery notes;
- blockers and missing evidence.

## Integrity rules

- Hash generated artifacts.
- Bind them to the run attempt and source identity.
- Preserve raw evidence separately from the human summary.
- Do not rewrite raw observations after adjudication; append a decision record.
- Redact secrets, tokens, cookies, personal data, and private paths.
- Treat screenshots and HAR/network summaries as evidence, not universal proof.

## Completion states

- `COMPLETE` — bounded matrix collected and integrity checks passed.
- `PARTIAL` — useful evidence exists but one or more declared cells are missing.
- `BLOCKED` — boundary, access, environment, or identity prevented collection.
- `NOT_RUN` — no execution evidence exists.

Only `COMPLETE` can support the highest claim level, and even then causality requires separate adjudication.
