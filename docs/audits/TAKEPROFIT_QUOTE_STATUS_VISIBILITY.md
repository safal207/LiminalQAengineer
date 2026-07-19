# TakeProfit quote-status visibility counterfactual

## Finding

**ID:** `TP-QUOTE-STATUS-07`  
**Status:** `CONFIRMED_PUBLIC_SURFACE`  
**Severity candidate:** `P2`  
**Confidence:** `HIGH`

> When current quote requests are unavailable, the public chart remains fully plausible and the only visible status change is the disappearance of a small green signal icon next to `BYBIT`.

No textual `Offline`, `Stale`, `Delayed`, `Disconnected`, `Reconnecting`, or freshness timestamp appears.

## Exact evidence

- Workflow run: `29666238811`
- Exact evidence head: `18d703929c31d53789814890a3565550283d5120`
- Artifact: `8435839001`
- Artifact digest: `sha256:6900d32df4805706dc1ec8cc9d19f409e079c9ebbde6b907fce20d0534328838`
- Raw result SHA-256: `cd57984cc134fd4ea99861e0640388fc712795eac4f86e637dd766fdbead0838`
- Runner evidence SHA-256: `d0fc1572b64d5c53ddaf7f60226f6ede2e232ba7af1c18727cc72ca33d8a62bf`

## Experiment

Three paired runs used fresh browser contexts:

```text
baseline
→ allow naturally initiated QuoteApi/ListQuotes requests

treatment
→ browser-locally block only naturally initiated QuoteApi/ListQuotes requests
```

Each variant opened the same public indicator page, waited for the visible chart, observed it for 20 seconds, and captured the exact chart crop.

| Pair | Baseline responses | Blocked treatment requests | Chart visible | Body text same | Material chart diff |
|---:|---:|---:|---|---|---:|
| 1 | 2 | 1 | yes | yes | 0.3214% |
| 2 | 1 | 2 | yes | yes | 0.3214% |
| 3 | 1 | 2 | yes | yes | 0.3214% |

All three baseline crops had the same SHA-256:

```text
72402381f037ca7afec422a9d8dcaa1cced117742811f8f63c195c289b9ffc79
```

All three treatment crops had the same SHA-256:

```text
005ab2fd1bed42c57fcf678afa196dc38a71f203ed4609b8daf42450c5e0eaa1
```

## Visual isolation

The exact raw pixel difference was repeated in all three pairs:

```text
bounding box: x=148..193, y=8..27
raw different pixels: 678
materially changed pixels: 621
```

Manual review of that bounded region shows:

### Baseline

```text
BTC/USDT  BYBIT  [small green live/connectivity signal]  1h
```

### Quote-block treatment

```text
BTC/USDT  BYBIT  1h
```

The candles, indicator lines, axes, visible price labels, and page body text remain unchanged. The `1h` control shifts left because the small signal icon is absent.

## Causal chain

```text
ListQuotes available
→ small green connection/live icon visible
→ chart remains visible

ListQuotes blocked
→ green icon disappears
→ no textual state replaces it
→ historical-looking chart remains fully plausible
→ user must notice the absence of a small icon to understand state loss
```

This is a narrower and stronger conclusion than the earlier stale-price hypothesis.

## Pythia

**Verdict:** `ALLOW_BOUNDED_STATUS_VISIBILITY_CLAIM`

Confirmed:

- the icon depends on current quote transport in 3/3 paired runs;
- the chart remains visible when that transport is unavailable;
- no textual freshness or connection state appears;
- the rest of the visible page text remains unchanged.

Not claimed:

- that visible candles are live;
- that the displayed `61516.2` value is a stale current quote;
- that the authenticated workspace behaves identically;
- that the endpoint is unused.

## CML

This finding refines two earlier memories:

1. The current quote request has a visible dependency, so the broad “unused quote polling” hypothesis is rejected.
2. The dependency is the small status icon, not a demonstrated update of the visible candle chart.

The ChartStore required-field regression still recurs in baseline and treatment. A shared root cause is not established.

## LS

The user-control defect is **state visibility**:

- the failure state is icon-only;
- the signal is small and based on absence rather than an explicit warning;
- the chart remains credible-looking;
- there is no timestamp explaining when visible market data was last updated;
- the body text offers no equivalent state for users who do not perceive the icon.

## Minimal fix

Preserve the chart if desired, but replace silent icon disappearance with an explicit state contract:

```text
Live · updated 2s ago
Delayed · last update 14:32:05
Offline · showing snapshot from 14:31:00
```

The state should be visible text, programmatically accessible, and tied to the exact data source displayed.

## Regression test

```text
block ListQuotes in browser-local test
→ chart may remain visible
→ visible text must show Offline / Delayed / Snapshot
→ last-updated timestamp must stop advancing
→ status must have an accessible name
→ restoring requests must return the state to Live
```

## Safety boundary

The treatment blocked only requests naturally initiated by one public page. It did not call the endpoint directly, authenticate, access account data, submit financial operations, fuzz, load test, exploit, or claim a security vulnerability.
