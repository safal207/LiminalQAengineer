# Starbucks Store Locator host-isolation result

## Decision

The corrected exact-host experiment confirms one bounded mobile dependency:

> When the single script request served from `maps.googleapis.com` is blocked, the Starbucks mobile Store Locator enters the same generic whole-application error state in 3/3 fresh contexts, loses Store Locator identity and all visible search inputs, and returns to the exact meaningful baseline after scripts are restored in 3/3 contexts.

Lotus result:

```text
Pythia: ALLOW
CML: PROPOSED_RECURRING
LS: MEDIUM
Decision: CONFIRMED
Severity: P2
```

This is a dependency and error-containment finding. It is **not** a finding of Google provider fault.

## Exact evidence

```text
workflow: Starbucks Store Locator Third-Party Host Isolation
run: 29676480938
head: 33608dcdc0f9854afab19a111469fd870e8037bd
artifact: 8439113486
artifact digest: sha256:8168beee4862a4514c9411954a4200e668eec7a46009a047b6e70760e6c0005e
result SHA-256: 527c7e3bc98c50f88027846eb726df38f91f990c9956d717f9f72ed7663a1b61
```

The run completed all 75 sequential public-browser navigations and all privacy and authority checks.

## Reproduction matrix

| Signal | Result |
|---|---:|
| Inventory presence | `3/3` |
| Baseline meaningful | `3/3` |
| Exact host script blocked | `3/3` |
| Blocked requests | `1` per round |
| Generic application error | `3/3` |
| Store Locator identity lost | `3/3` |
| Visible inputs during treatment | `0/3` in every round |
| Recovery meaningful | `3/3` |

All three treatment rounds produced the same fingerprints:

```text
text SHA-256:
bff2809e8233695f89a181f75e9bb83f063cca684be660ca16194d9b84e9758c

screenshot SHA-256:
ccc060ecfae5be2c1e5ef12d6266b3d311c24561a2f95283289af6a4eb818ddc
```

All baseline and recovery rounds produced the same fingerprints:

```text
text SHA-256:
fe643216022aea97ae630ffd3a1f8a23702c897d905e17979c39e975f1cda7c6

screenshot SHA-256:
258ecd3ae8761427c5df3c25472fc962dccfa9188734840b8e08281c6e6756a3
```

This provides both repeated failure and exact recovery evidence.

## Negative causal memory

Seven other stable script hosts were blocked independently in three fresh contexts each:

- `www.googletagmanager.com`;
- `bat.bing.com`;
- `consent.trustarc.com`;
- `mpsnare.iesnare.com`;
- `googleads.g.doubleclick.net`;
- `jssdkcdns.mparticle.com`;
- `prod.accdab.net`.

For every host:

```text
blocked: 3/3
meaningful treatment: 3/3
generic error: 0/3
recovery: 3/3
```

Therefore the broad claim that any stable third-party script independently causes the crash is blocked and preserved as `NEGATIVE_CAUSAL_MEMORY`.

## Remaining evidence gap

`resources.xg4ken.com` appeared in all three inventory rounds but ranked ninth and was excluded by the preconfigured eight-host cap.

Lotus result:

```text
Pythia: ESCALATE
CML: CONFLICT
LS: UNKNOWN
Decision: NEEDS_EVIDENCE
Severity: UNASSIGNED
```

No causal or neutral conclusion is assigned to that host.

## Causal boundary

Confirmed:

```text
maps.googleapis.com script unavailable
→ mobile Store Locator reaches a generic application error boundary
→ search inputs and route identity disappear
→ restoring the script restores the exact baseline
```

Not confirmed:

- that Google caused the defect;
- that the Google Maps service itself was unavailable;
- that desktop has the same failure;
- that every production session is affected;
- that this is a security vulnerability.

The root cause may remain in Starbucks integration code, loading order, mobile feature detection, timeout behavior, or placement of the application error boundary.

## Minimal correction

1. Catch Maps JavaScript loading and initialization failures inside the map component.
2. Keep a store-name/location search or accessible list fallback available.
3. Explain that the map could not load instead of replacing the complete application.
4. Provide a specific retry action and support route.
5. Test script rejection, timeout, invalid initialization, and delayed loading independently.

## Regression contract

```text
Given the mobile Store Locator loads normally
When the maps.googleapis.com script fails or times out
Then the whole application must not enter a generic crash screen
And Store Locator identity remains visible
And an accessible search or store-list fallback remains usable
And the error explains the failed map dependency
And retry restores the map without requiring a full application restart
```

## Authority

The packet is audit-only and artifact-only. It grants no ownership, approval, execution, delivery, external submission, deployment, or merge authority. Durable CML acceptance remains subject to explicit human review.
