# Starbucks Store Locator xg4ken Control v0.1

## Goal

Close the final untested host cell from the mobile Store Locator host-isolation audit.

`resources.xg4ken.com` appeared in all three inventory rounds but ranked ninth, outside the original eight-host cap. This experiment tests that host directly instead of inferring safety or causality from rank.

## Exact experiment

```text
mobile Store Locator
→ 3 fresh contexts
→ baseline
→ block only resources.xg4ken.com script requests
→ recovery with scripts restored
```

Nine sequential browser navigations are performed in total.

## Decision contract

`SUPPORTED_HOST_DEPENDENCY` requires all three rounds to show:

1. the target script host is naturally requested during baseline;
2. baseline Store Locator is meaningful;
3. at least one script request from the exact host is blocked;
4. the same generic application error appears;
5. Store Locator identity disappears;
6. recovery restores meaningful Store Locator state.

`NEUTRAL_UNDER_BOUNDED_TEST` requires all three rounds to show:

1. the target script host is naturally requested during baseline;
2. baseline is meaningful;
3. the exact host is blocked;
4. treatment remains meaningful;
5. no generic application error appears;
6. recovery remains meaningful.

Mixed or incomplete evidence remains `NEEDS_EVIDENCE`.

## Evidence retained

- normalized route and exact host;
- request, response, failure, and status counts;
- target-host script request and block counts;
- visible landmark, input, button, and link counts;
- route-identity booleans;
- generic-error and recovery-guidance booleans;
- accessibility-tree counts;
- body-text SHA-256 and length, not body text;
- screenshot files and SHA-256;
- console and page-error hashes and lengths, not text.

## Privacy and safety

The experiment does not retain request or response bodies, headers, cookies, storage, form values, credentials, console text, or page-error text.

It performs no authentication, account creation, form submission, orders, payments, Gift or Rewards mutation, direct application API calls, credential validation, crawling, fuzzing, load testing, active security testing, external submission, or vulnerability claim.

## Interpretation boundary

A neutral result means only that blocking this host did not cross the deterministic failure threshold in this bounded mobile Store Locator scenario.

A supported dependency means the host is a reproducible trigger under this scenario. It does not establish provider fault; integration code, loading order, feature detection, fallback behavior, and error containment remain possible root causes.

## Authority

```text
ownership = false
approval = false
execution = false
delivery = false
external_submission = false
deployment = false
merge = false
```
