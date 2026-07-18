# TakeProfit Lotus Decision Packet 🌸

## Executive decision

**Decision:** `ESCALATE`  
**Stop reason:** `CONFIRMED_STATE_AMBIGUITY_AND_UNRESOLVED_ORDERING_BOUNDARY`

The packet combines exact LiminalQA evidence with three advisory readings:

```text
LiminalQA evidence
→ Pythia: what is proven and what remains uncertain
→ CML: what repeats across time and runs
→ LS: where the user loses visibility or control
→ human-reviewed decision packet
```

It does not authorize additional testing, report submission, product changes, approval, delivery, execution, or merge.

## Exact evidence

### Stale-quote counterfactual

- workflow run: `29664173396`;
- exact head: `2584c21587f54d6d3c9680ccdb41d86d028cabd3`;
- artifact digest: `sha256:0a8574204b3a802278928c7213c235421bd79c5186dbd48eac7a0423f5970a2b`;
- raw result digest: `sha256:5e7ed2c55d8b7af9f1b5a9809df25e623296c319f635ca1cea246f7dc948307b`.

The second naturally initiated `ListQuotes` response was held in the browser for **76,041 ms**.

During that period:

- the BTC/USDT chart stayed visible;
- no `stale`, `delayed`, `offline`, `disconnected`, or `reconnecting` state appeared;
- four later quote-response events occurred;
- the held older response was delivered after newer responses;
- the chart remained visible after release.

This confirms the stale-state visibility gap. It also creates an out-of-order transport condition, but does not prove that the application applied the old response or rolled the displayed price backward.

### Lotus packet build

- workflow run: `29664342786`;
- exact head: `b8fcf8afab18f890f25e8ef530a8ebb0b7928153`;
- artifact digest: `sha256:3addcaf8f7a9a75db05cb96b5b65542b12806414e5d0afd19d48fd95ad492482`;
- generated JSON digest: `sha256:a73f707597ee6e5cedd83ded0c3cc1b8620f6c5b40cf6467384b152bbd2a49de`;
- generated Markdown digest: `sha256:bd802e564cc03c36ac786e5536c6def7dda7f0ff759c8c84bcbc1e7ae5e64eed`.

## Decision table

| Case | State | Pythia | CML | LS |
|---|---|---|---|---|
| `TP-CHART-STATE-01` | `CONFIRMED_REPEATED_FAMILY` | `CONFIRMED` | `REPEATED_FAMILY` | `DEGRADED_BUT_PARTIALLY_HIDDEN` |
| `TP-QUOTE-STATE-02` | `CONFIRMED_REPEATED` | `CONFIRMED` | `REPEATED_BEHAVIOR` | `INFORMED_CONTROL_REDUCED` |
| `TP-QUOTE-ORDER-03` | `TRANSPORT_CREATED_APPLICATION_UNVERIFIED` | `ESCALATE` | `EXPERIMENTAL_CANDIDATE` | `RISK_NOT_YET_USER_VISIBLE` |

## TP-CHART-STATE-01 · Incomplete ChartStore initialization

### Pythia

**Verdict:** `CONFIRMED`  
**Confidence:** high.

Current evidence shows the required-field signature on initial load and after reload:

```text
[ChartStore] settings.chart.timeToCloseLabel is a required field
settings.chart.style.lineSource is a required field
settings.chart.style.tpo is a required field
```

Uncertainty remains explicit:

- the public chart continues rendering;
- downstream feature breakage was not demonstrated in this run;
- the authenticated workspace may use a different initialization path;
- repetition across January and July does not prove one unchanged implementation cause.

### CML

**Memory state:** `REPEATED_FAMILY`.

January reports contained missing `IndicatorManager`, crosshair, drawing, sync, and version fields. The current signature contains different missing ChartStore fields. CML preserves both revisions and links them as a recurring required-state family; it does not silently replace the old observations or convert correlation into confirmed causality.

### LS

**User-control state:** `DEGRADED_BUT_PARTIALLY_HIDDEN`.

A visible chart implies successful initialization, while the internal state contract is already violated. An ordinary user cannot see the degraded state or choose a repair action. Later indicator, drawing, persistence, or reload failures may appear unrelated to the original initialization fault.

### Minimal fix

Create one versioned, schema-valid chart-settings constructor. Migrate old persisted objects before ChartStore creation. Repair or reject incomplete state before consumers subscribe and before the chart is presented as ready.

## TP-QUOTE-STATE-02 · Stale quote lacks a freshness boundary

### Pythia

**Verdict:** `CONFIRMED`  
**Confidence:** high for the tested public surface.

The behavior reproduced under both a short browser-level interruption and a 76-second delayed-response counterfactual. The chart remained plausible without a freshness marker.

The following claims are not made:

- that the authenticated workspace behaves identically;
- that an order could be placed from this surface;
- that the exact visual quote age can be reconstructed from the canvas.

### CML

**Memory state:** `REPEATED_BEHAVIOR`.

The five-second interruption and the longer response-hold experiment are distinct evidence runs with the same user-visible outcome. This supports durable memory of the behavior, not proof of a shared root implementation with the ChartStore validation defect.

### LS

**User-control state:** `INFORMED_CONTROL_REDUCED`.

A stale but believable value is more dangerous than an obvious blank state. The user cannot tell whether to trust the chart, wait, refresh, or disregard the value. Freshness should be challengeable through a last-update timestamp and explicit states such as `fresh`, `delayed`, `reconnecting`, `offline — last known`, and `no data`.

### Minimal fix

Track the last successful symbol-bound market-data timestamp separately from page connectivity. Show a stale or delayed state after the expected heartbeat and clear it only after newer data for the same symbol arrives.

## TP-QUOTE-ORDER-03 · Older response delivered after newer responses

### Pythia

**Verdict:** `ESCALATE`.

The transport condition was created and observed: four later quote-response events occurred while response #2 was held, then the older response was released afterward.

Application effect remains unverified because the public canvas does not expose:

- quote sequence;
- server timestamp;
- applied-state sequence;
- symbol-bound last-update identity.

Therefore the packet does not claim a visible price rollback.

### CML

**Memory state:** `EXPERIMENTAL_CANDIDATE`.

The condition should be retained for the next authorized test but must not be stored as a confirmed user-facing defect yet.

### LS

**User-control state:** `RISK_NOT_YET_USER_VISIBLE`.

User impact becomes confirmed only if an older response visibly overwrites a newer value, mixes symbols, changes precision incorrectly, or makes timestamps inconsistent.

### Next experiment

Instrument the client-visible state with symbol, server timestamp, request sequence, and applied sequence. Deliver response A after response B and assert that A is rejected. Repeat across symbol and timeframe transitions.

## Regression contract

1. No ChartStore required-field error on cold load or reload.
2. A delayed quote beyond the heartbeat produces a visible freshness warning.
3. Last-known value remains timestamped and explicitly labelled.
4. A warning clears only after newer matching-symbol data arrives.
5. Older quote responses cannot overwrite newer applied state.
6. Symbol, candles, indicators, price marker, legend, and timestamp transition atomically.

## Authority boundary

Lotus is advisory. Pythia may judge evidence, CML may preserve causal memory, and LS may describe loss of human control. None of them owns the product, approves a fix, submits a report, performs external execution, delivers changes, or merges code.

> Memory is not permission. Verdict is not execution. `ESCALATE` is not punishment.
