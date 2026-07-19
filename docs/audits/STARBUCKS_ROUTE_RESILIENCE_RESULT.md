# Starbucks Route Resilience Result v0.1

## Exact run

```text
head: 1f7d330df7018ed28ee500a04ff7dcbaa0b21c28
workflow run: 29667373889
artifact: 8436241393
artifact digest: sha256:4fd8eb493d0a20b66d5d0f3a794ed597bf92c7a831366edf987dfa3470376a88
aggregate SHA-256: cd2dde59145998b5c555ffbe07f73031e9d5e8d978bc116212f644d54cc7470a
summary SHA-256: dbfd6747d6b4ba25ea87719ef5b81d2b29dd5b87c74a422bd5f7f543d48f1763
```

The artifact contains 152 manifest entries and approximately 41.5 MB of screenshots and structured evidence.

## Matrix result

```text
5 routes
× 2 profiles
× 3 fresh contexts
× 4 states
= 120 navigations
```

- 30 fresh private browser contexts;
- 10 route/profile cells;
- 9 `SUPPORTED_FINDING` cells;
- 1 `NEEDS_EVIDENCE` cell.

| Route | Profile | Baseline | Third-party control | First-party terminal | Recovery | Result |
|---|---|---:|---:|---:|---:|---|
| menu | desktop | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| menu | mobile | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| store locator | desktop | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| store locator | mobile | 3/3 | 0/3 | 3/3 | 3/3 | third-party control confounded |
| sign-in | desktop | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| sign-in | mobile | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| rewards | desktop | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| rewards | mobile | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| gift | desktop | 3/3 | 3/3 | 3/3 | 3/3 | supported |
| gift | mobile | 3/3 | 3/3 | 3/3 | 3/3 | supported |

## Finding 1: silent first-party JavaScript failure

Every first-party-script treatment blocked at least one Starbucks-hosted script.

Across all 30 treatment pairs:

```text
visible main landmark: absent 30/30
route identity: absent 30/30
visible inputs: absent 30/30
JavaScript-required explanation: absent 30/30
route-specific recovery guidance: absent 30/30
recovery after scripts restored: 30/30
```

Only two treatment screenshot hashes appeared across all routes and rounds, corresponding to desktop and mobile generic shells. The route-specific task disappeared while a plausible header or cookie-consent surface remained.

This is narrower and stronger than the earlier text-client observation:

- the text client saw a JavaScript-required sentence;
- the real-browser fault treatment did **not** show that explanation;
- the visitor instead saw a generic shell or cookie dialog with the requested task missing.

### Causal boundary

First-party causality is fully isolated in nine route/profile cells because the third-party-script control retained route identity in all three rounds and recovery succeeded in all three rounds.

The mobile store locator is excluded from that isolation count because its third-party control also failed.

### Lotus result

```text
ID: SBX-WEB-FIRST-PARTY-JS-SILENT-SHELL-001
Pythia: ALLOW
CML: PROPOSED_RECURRING
LS: MEDIUM
Decision: CONFIRMED
Severity: P2
```

## Finding 2: mobile store locator third-party failure boundary

When all third-party scripts were blocked on the mobile profile, the store locator produced the same generic error screen in 3/3 fresh contexts:

```text
Whoops, something went wrong
The app had an error it couldn't recover from
Refresh
```

Exact repeated evidence:

```text
navigation status: 200
blocked third-party scripts: 5 per round
route identity retained: 0/3
recovery guidance visible: 3/3
recovery after scripts restored: 3/3
text SHA-256: 931f63535bd8f5f6913bfd86815073908bfd1e8a85b2c055683770de327b2047
screenshot SHA-256: ce119f88b6aed4acab25b0ae03912158e697122ae12752cf601de4791e0e6fc1
```

The equivalent desktop control retained store-locator route identity in 3/3 runs.

### What is confirmed

- the mobile store locator has a hard degraded-state boundary under the combined third-party-script treatment;
- the error is deterministic in this exact laboratory profile;
- the error is visible and offers refresh;
- the route does not identify the failed dependency or preserve a basic store-search fallback.

### What is not confirmed

- which of the five blocked third-party scripts is necessary;
- whether the responsible dependency is mapping, telemetry, experimentation, anti-abuse, or another provider;
- whether the same failure occurs naturally in production traffic;
- whether one specific third party is a product defect.

### Lotus result

```text
ID: SBX-STORE-LOCATOR-MOBILE-THIRD-PARTY-ERROR-001
Pythia: ALLOW
CML: PROPOSED_RECURRING
LS: MEDIUM
Decision: CONFIRMED
Severity: P2
Provider identity: UNKNOWN
```

## What the first report missed

The original Starbucks memo treated JavaScript dependency as one broad issue. The controlled matrix revealed two different failure contracts:

1. **First-party failure:** silent loss of the requested task while a generic shell remains.
2. **Third-party mobile store-locator failure:** explicit generic application crash with refresh guidance.

Those should not share one root cause or one regression test.

## Next bounded experiment

The mobile store-locator result should be decomposed by third-party host or script group:

```text
working mobile baseline
→ block one third-party host only
→ capture route identity and error boundary
→ restore
→ repeat three fresh contexts
```

A provider-specific claim remains blocked until one host or script group reproduces the generic error independently.

## Safety and authority

The experiment used public browser navigation only, one page at a time. It performed no authentication, form submission, order, payment, gift-card balance check, Rewards mutation, direct application API call, credential validation, token request, fuzzing, load testing, bypass, or active security testing.

No request or response bodies, headers, cookies, web storage, form values, credentials, or authentication material were retained.

```text
ownership = false
approval = false
execution = false
delivery = false
deployment = false
merge = false
durable_memory = false
write_mode = artifact_only
```
