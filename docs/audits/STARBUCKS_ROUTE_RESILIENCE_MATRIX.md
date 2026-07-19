# Starbucks Public Route Resilience Matrix v0.1

## Goal

Test whether the bounded non-JavaScript behavior recorded in the Starbucks Lotus audit is reproducible in a real browser, whether it is specifically caused by first-party JavaScript loss, and whether the page recovers when scripts return.

The experiment keeps four states separate:

```text
normal baseline
→ third-party scripts blocked control
→ first-party Starbucks scripts blocked treatment
→ first-party scripts restored recovery
```

It does not treat a JavaScript dependency as an automatic accessibility-conformance failure.

## Matrix

Five public routes:

- `https://www.starbucks.com/menu`
- `https://www.starbucks.com/store-locator`
- `https://www.starbucks.com/account/signin`
- `https://www.starbucks.com/rewards`
- `https://www.starbucks.com/gift`

Two profiles:

- desktop `1440 × 1000`;
- mobile `390 × 844`.

Three fresh browser contexts per route and profile.

Each context performs four sequential navigations, for exactly:

```text
5 routes × 2 profiles × 3 rounds × 4 states = 120 navigations
```

Only one page is active at a time.

## What is captured

For every state:

- navigation status;
- normalized final URL without query parameters;
- visible text length and SHA-256, not raw body text;
- route-identity term matches;
- JavaScript-required and recovery-guidance indicators;
- visible main, navigation, link, button, and input counts;
- accessibility-tree node and role counts;
- screenshot and SHA-256;
- first-party and third-party request counts;
- script request and blocked-script counts;
- response status counts;
- hashes and lengths of bounded console and page-error messages.

The artifact does not store request or response bodies, request headers, cookies, web storage, form values, authentication material, or credentials.

## Causal control

A first-party JavaScript terminal-state finding is emitted only when all three rounds for the same route and profile satisfy all four conditions:

1. the baseline has meaningful content, a visible main landmark, route identity, and no JavaScript-required message;
2. blocking third-party scripts retains meaningful route behavior;
3. blocking at least one first-party Starbucks script produces a terminal or structurally empty state;
4. restoring scripts restores meaningful route behavior.

If third-party blocking also breaks the page, the first-party claim is marked confounded rather than confirmed.

## Why cache and service workers are disabled

A baseline navigation can otherwise populate script cache or service-worker responses. Later treatment phases might appear to block first-party scripts while the browser silently reuses cached code.

Each context therefore:

- bypasses service workers;
- disables browser cache through CDP;
- uses a fresh private browser context;
- stops lingering activity before the next treatment.

## Decision states

### `SUPPORTED_FINDING`

All three rounds isolate a first-party JavaScript terminal state and recover after scripts return.

### `NEEDS_EVIDENCE`

Used when:

- baseline behavior is unstable;
- no first-party script request was actually blocked;
- terminal behavior is intermittent;
- the third-party control also breaks;
- recovery does not consistently restore the route.

### `PASS`

No deterministic terminal state crosses the configured threshold.

## Safety boundary

- public browser navigation only;
- no authentication or account creation;
- no form submission;
- no order, payment, gift-card balance, or Rewards mutation;
- no direct application API calls;
- no credential validation or token requests;
- no crawling, fuzzing, load testing, bypass, or active security testing;
- no external submission or vulnerability claim;
- audit-only authority with no ownership, approval, execution, delivery, deployment, or merge grant.

## Relationship to the Lotus packet

The experiment can strengthen or reject `SBX-WEB-JS-DEPENDENCY-001` by adding exact browser evidence.

It cannot by itself confirm `SBX-A11Y-NOJS-WCAG-HYPOTHESIS-001`. Any later accessibility claim still requires a mapped success criterion, supported environment, keyboard or assistive-technology task, and reproducible user impact.

A later result must be appended as a new observation and may supersede the current measurement state without deleting the original bounded text-client observation.
