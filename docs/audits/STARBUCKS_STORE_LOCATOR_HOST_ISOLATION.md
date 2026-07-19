# Starbucks mobile Store Locator third-party host isolation v0.1

## Purpose

The route-resilience matrix found that blocking all third-party scripts caused the mobile Store Locator to show a generic unrecoverable application error in 3/3 rounds, while desktop remained meaningful.

That experiment proved a grouped third-party dependency but could not identify a specific host. This follow-up prevents attribution by guesswork.

```text
three fresh inventories
→ retain stable third-party script hosts only
→ block one host at a time
→ three fresh contexts per host
→ restore scripts and verify recovery
```

## Exact scope

- target: `https://www.starbucks.com/store-locator`;
- profile: mobile `390×844`;
- three inventory rounds;
- hosts must appear in at least two inventory rounds;
- no more than eight candidate hosts;
- three isolation rounds per candidate;
- baseline → one-host block → recovery;
- maximum 75 sequential navigations.

## Supported dependency threshold

A host receives `SUPPORTED_HOST_DEPENDENCY` only when all three rounds show:

1. meaningful baseline route identity;
2. at least one script from that exact host was blocked;
3. the same generic application error appeared;
4. Store Locator identity disappeared;
5. recovery restored a meaningful Store Locator.

A host remains `NEUTRAL_UNDER_BOUNDED_TEST` when blocking it is confirmed but Store Locator stays meaningful in 3/3 rounds.

Mixed outcomes remain `NEEDS_EVIDENCE`.

## What the result can establish

The experiment may identify a host whose script absence is a necessary trigger for the observed mobile error under this profile and time window.

It cannot by itself establish whether the true root cause is:

- provider behavior;
- Starbucks integration code;
- script loading order;
- consent or privacy configuration;
- mobile-only feature detection;
- inadequate error containment.

Host dependency is therefore narrower than provider fault.

## Evidence retained

- stable third-party script hostnames and counts;
- status counts;
- exact blocked-script counts;
- route-identity and generic-error booleans;
- visible landmark, control, and input counts;
- accessibility-tree role counts;
- screenshots and SHA-256;
- console and page-error hashes and lengths;
- exact aggregate and summary hashes.

## Data excluded

- request and response bodies;
- request and response headers;
- cookies and web storage;
- form values;
- console and page-error text;
- authentication or account material;
- candidate, customer, payment, gift-card, or Rewards data.

## Decision boundary

```text
host-level trigger ≠ provider culpability
correlation in 3/3 ≠ universal production failure
mobile profile evidence ≠ desktop failure
public browser observation ≠ vulnerability claim
```

The output is advisory, artifact-only evidence. It grants no ownership, approval, external-submission, execution, deployment, or merge authority.
