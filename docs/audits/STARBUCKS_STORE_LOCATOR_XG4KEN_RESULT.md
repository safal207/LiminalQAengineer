# Starbucks Store Locator xg4ken Control Result

## Result

`resources.xg4ken.com` is a confirmed neutral control in the bounded mobile Store Locator experiment.

```text
host naturally requested
→ block exactly one script request
→ Store Locator remains meaningful
→ no generic error
→ visible and accessibility state unchanged
→ recovery remains identical
```

## Exact evidence

```text
workflow run: 29677168104
exact head: 86c9e6613aee666d5433386b5384a642d6b3e168
artifact: 8439296088
artifact digest: sha256:77fc768bafbb39cc3e9aeb013e12a3b03257195428c53cb28f750edd7ffbb293
aggregate file SHA-256: c05878f7f52fc3a92c58828695d4dff5a54ec077a9eddb63486a7e14ebd76421
result SHA-256: a5ab902a4b9a53125ba08293cce1755750c58fc53ba7810efaf3adebba0e6509
```

## Three-round outcome

| Signal | Result |
|---|---:|
| Host naturally requested | 3/3 |
| Meaningful baseline | 3/3 |
| Exact host script blocked | 3/3 |
| Generic application error | 0/3 |
| Route identity lost | 0/3 |
| Meaningful treatment | 3/3 |
| Meaningful recovery | 3/3 |

Every baseline, treatment and recovery state shared the same fingerprints:

```text
text SHA-256:
fe643216022aea97ae630ffd3a1f8a23702c897d905e17979c39e975f1cda7c6

screenshot SHA-256:
4cdc9a88ba64a712ca1d3f140c7b62182d73c091f2b8d1b60a6cc72212c1eb93
```

The structural state was also unchanged:

```text
visible inputs = 3
main landmarks = 1
visible links = 8
visible buttons = 9
accessibility nodes = 300
```

## Causal conclusion

The earlier `SBX-STORE-XG4KEN-UNTESTED-001` state is superseded.

`resources.xg4ken.com` does not independently reproduce the mobile Store Locator failure under this exact experiment. The confirmed Maps dependency remains isolated from this host.

This is bounded evidence, not a universal statement about every page, region, consent state or future implementation.

## Lotus expectations

### Confirmed neutral control

```text
Pythia: ALLOW
CML: PROPOSED_RECURRING
LS: NONE
Decision: CONFIRMED
Severity: P3
```

### Rejected crash hypothesis

```text
Pythia: BLOCK
CML: NEGATIVE_CAUSAL_MEMORY
LS: NONE
Decision: BLOCKED
Severity: UNASSIGNED
```

## Remaining causal graph

```text
maps.googleapis.com unavailable
→ confirmed whole-app mobile Store Locator failure

resources.xg4ken.com unavailable
→ no observed visible or accessibility change

seven other isolated stable hosts unavailable
→ no independent crash in their bounded controls
```

The grouped third-party failure is therefore narrowed to the Maps script dependency rather than generalized to external scripts as a class.

## Safety and authority

Public browser navigation only. No authentication, account creation, form submission, direct application API calls, payment, Gift, Rewards, customer data, fuzzing, load testing, active security testing, external submission, vulnerability claim, execution authority or merge authority.
