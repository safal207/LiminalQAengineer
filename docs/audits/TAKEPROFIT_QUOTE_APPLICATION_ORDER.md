# TakeProfit quote application-order audit

## Executive result

The three-round experiment did **not** confirm a visible quote rollback.

It produced a more useful correction:

> The public published-indicator chart is not proven to consume the current `ListQuotes` payload at all.

The naturally initiated quote payload changed between observations, but the chart crop remained byte-identical throughout each 90-second hold and after the delayed response was released.

## Exact evidence

- Workflow run: `29665870021`
- Exact evidence head: `d9d5e2d08c20bea2296f0c167565642121cd9874`
- Artifact: `8435761035`
- Artifact digest: `sha256:93f8238f436ec5b3fd7d7f8cd6fb167b517c0f546c02c34dc21c00018a10d20a`
- Raw result SHA-256: `031b61578fa9982ad89b8245a64331bc054ebc8a23ca498b4159193f089ff560`
- Runner evidence SHA-256: `4a09e4a607c50b74f59a3029914242859b1f5cfa5e734a3e9c6b76d41cc2f8fa`

## What happened in every round

1. The page loaded one non-empty current quote response.
2. The next non-empty quote response was held in the browser for about 90 seconds.
3. No later non-empty quote response was initiated while that response remained pending.
4. No `stale`, `delayed`, `offline`, `disconnected`, or `reconnecting` state appeared.
5. The visible chart crop did not change during the hold or after release.
6. The ChartStore missing-required-field error appeared again.

| Round | First payload decimal candidate | Held payload decimal candidate | Hold | Newer responses | Chart crop |
|---:|---:|---:|---:|---:|---|
| 1 | 64835.7 | 64835.6 | 90,545 ms | 0 | unchanged |
| 2 | 64816.9 | 64816.8 | 90,375 ms | 0 | unchanged |
| 3 | 64812.6 | 64812.5 | 90,554 ms | 0 | unchanged |

The decimal values are derived from repeated protobuf mantissa/scale pairs in the public gRPC-web response. The exact business field name is not asserted without the service schema.

The visible chart showed right-axis labels including `61516.2` and `59235.6`, and every captured crop had the same SHA-256:

```text
72402381f037ca7afec422a9d8dcaa1cced117742811f8f63c195c289b9ffc79
```

## Causal correction

The earlier delayed-response experiment proved that an older response could be delivered after newer responses during initial page bootstrap.

This experiment held the **second** non-empty response instead. In three rounds, no later non-empty response started while it was pending.

```text
steady-state quote request pending
→ next poll is not started
→ no steady-state response overlap
→ no steady-state older-after-newer application path created
```

Therefore the previous overlap should be scoped to the first-load request family until another surface proves otherwise.

## Pythia judgment

**Verdict:** `ESCALATE`

**Stop reason:** `VISIBLE_CHART_IS_NOT_PROVEN_TO_CONSUME_CURRENT_QUOTES`

### Confirmed

- steady-state polling was serialized in 3/3 rounds;
- the chart remained visually unchanged during 3/3 long holds;
- no freshness or connection-state marker appeared;
- ChartStore required-field validation recurred in 3/3 rounds.

### Blocked claims

- the public chart visibly rolled back to an older quote;
- `61516.2` was a stale current BTC price;
- the authenticated workspace uses the same transport or chart policy.

## CML reading

The causal memory is refined rather than expanded:

```text
initial page bootstrap
→ overlapping quote request family can occur
→ older-after-newer delivery can be created

steady-state scheduled poll
→ pending response suppresses the next non-empty poll
→ overlap was not reproduced
```

The ChartStore regression remains correlated evidence. It is not established as the cause of quote polling or static chart behavior.

## LS reading

The strongest user-control question is now **live versus historical clarity**, not a confirmed stale live price.

The page presents a plausible financial chart and loads current quote payloads, but the visible surface does not clearly establish whether the chart is:

- live;
- delayed;
- a fixed historical snapshot;
- or a published chart state captured at another time.

That ambiguity requires product-intent evidence before severity is assigned.

## New candidates

### 1. Current quote polling may have no visible dependency

A browser-local block-versus-baseline counterfactual can determine whether `ListQuotes` affects the public chart, visible metadata, errors, or interactions.

Until then this remains a candidate, not a confirmed waste defect.

### 2. Startup overlap needs its own application-order experiment

The first-load duplicate request family is the only state where natural overlap has been observed. It should be tested separately with chart-only pixel evidence.

### 3. Published charts need an explicit state contract

A small `Live`, `Delayed`, or `Snapshot as of …` label would remove the ambiguity regardless of the transport implementation.

## Safety boundary

The workflow used one public allowlisted page and delayed only responses naturally initiated by that page. It did not authenticate, call the endpoint directly, access account data, submit financial operations, fuzz, load test, exploit, or claim a security vulnerability.
