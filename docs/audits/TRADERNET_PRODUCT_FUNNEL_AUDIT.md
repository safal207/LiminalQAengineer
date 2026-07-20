# Tradernet product-funnel UX audit

**Version:** `v0.1`  
**Date:** `2026-07-21`  
**Scope:** public unauthenticated desktop and mobile web, plus bounded product hypotheses for authenticated trading journeys  
**Method:** Product Manager review + Lotus Product Lens + ethical ClickFunnels pattern analysis + LiminalQA evidence chain

## Executive decision

Tradernet already exposes substantial brokerage and analytical capability, but the public journey is organised more like a collection of product surfaces than a guided path from intent to realised value.

The highest-value product shift is not "add more features". It is:

```text
intent
→ relevant promise
→ low-risk first value
→ account creation
→ guided activation
→ comprehensible financial action
→ visible result
→ recovery and return
```

The current public evidence supports four technical/product findings for human reporting:

1. `P1` — a public chart route returns the generic 404 experience for mobile user-agents;
2. `P1-performance` — late mobile hero discovery materially delays meaningful content;
3. `P2` — mobile terminal entry downloads a hidden `346,800` byte image;
4. `P3` — terminal entry requests a missing first-party onboarding asset.

Authenticated order-entry, portfolio, KYC, funding, cancellation, Stop Loss and Take Profit recommendations in this document are **product hypotheses and test requirements**, not claimed defects. They remain `NEEDS_AUTHENTICATED_EVIDENCE` until reproduced against an authorised test account and exact build.

## Authority and safety boundary

This audit is advisory and audit-only. It does not:

- access private accounts or portfolio data;
- place, modify or cancel orders;
- perform load, fuzz or destructive testing;
- make a security-vulnerability claim;
- contact Tradernet automatically;
- approve pricing, experiments, deployment, delivery or merge.

A human product owner decides what to validate, prioritise, report, experiment on or ship.

## Evidence chain

### Source repository

- Repository: `safal207/LiminalQAengineer`
- Exact source base: `d1caf64db824aeb6486d1e741b999f74533e29b7`
- Relevant merged audits: PRs `#54`, `#58`, and `#60`

### Existing judgment layers

- Pythia external-QA judgment: `safal207/pythiaLabs` PR `#235`, head `aa169a3a897a61bb578816ea9e8fb3e374405b34`
- CML public memory pack: `safal207/Causal-Memory-Layer` PR `#213`, head `0a3995e2508d204cdff2a6817563fa7e3f7a46fe`
- LS human-impact scorecard: `safal207/LS` PR `#919`, head `daab61e653d380e258df9db6bc13057315846c64`
- Lotus Product Lens contract: `safal207/LS` PR `#920`, head `44087899bdaad86b32b13d89812cbf7a174db2fe`

The product-lens contract is used as a review framework only. ClickFunnels and SamCart are pattern references; their marketing claims are not evidence for Tradernet.

## Evidence labels

| Label | Meaning |
|---|---|
| `CONFIRMED` | Reproduced public behaviour with exact run or artifact evidence. |
| `SUPPORTED` | Multiple observations support the conclusion, but it is not a complete causal proof. |
| `HYPOTHESIS` | Product or causal interpretation requiring a controlled test. |
| `NEEDS_AUTHENTICATED_EVIDENCE` | Cannot be claimed from public unauthenticated evidence. |
| `UNKNOWN` | Evidence is insufficient or conflicting. |

## Product jobs

Tradernet should not treat all visitors as one audience. The main jobs are materially different.

| Segment | Primary job | Product anxiety | First meaningful value |
|---|---|---|---|
| New investor | Start without making an avoidable mistake | "I do not understand the platform or the consequences" | Build a watchlist and preview a simulated action |
| Long-term investor | Understand portfolio state and required attention | "What changed and what should I inspect?" | Clear portfolio summary and attention queue |
| Active trader | Analyse and execute quickly without losing context | "Will the system behave as I expect right now?" | Market state, live/delayed data, order preview and fast recovery |
| Returning mobile user | Check state and perform one short action | "I have little time and a small screen" | Position/order card with explicit next action |
| Interrupted user | Restore an unfinished intention safely | "Did my action submit, fail or remain a draft?" | Exact state, refreshed data and a bounded recovery path |

## Current product-path diagnosis

The public journey is likely experienced as:

```text
broad promise
→ registration
→ identity and account steps
→ platform surfaces
→ user discovers their own workflow
```

The recommended journey is:

```text
segment intent
→ specific promise
→ demo or low-risk first value
→ minimal registration
→ activation checklist
→ KYC and funding when required
→ financial-action preview
→ confirmation
→ visible execution state
→ recovery, protection and return
```

## Lotus Product Lens review

### 1. Intent before conversion — `FRICTION_RISK`

The public entry should distinguish at least three intents:

- start investing;
- actively trade;
- explore in demo.

A single broad promise forces visitors to translate the product into their own use case before they trust the next step.

**Bounded experiment:** compare a generic entry page against a three-intent entry page. Measure meaningful next-step completion, not clicks alone.

### 2. Continuity before friction — `RECOVERY_GAP`

The journey should preserve:

- selected intent;
- language;
- selected instrument;
- demo/real state;
- unfinished onboarding step;
- unfinished order draft;
- last confirmed server state.

This is especially important on mobile where interruption is normal.

### 3. Complementary value before upsell — `VALUE_UNPROVEN`

Brokerage growth prompts, premium data, margin, additional instruments or related offers should be presented only when relevant to the current job. No paid or risk-increasing choice should be preselected.

### 4. One click without hidden commitment — `FRICTION_RISK`

Before any financial commitment, the interface should show:

- exact instrument and direction;
- quantity and order type;
- estimated price and total;
- fee and currency-conversion implications;
- recurring or subscription terms when applicable;
- market-session state;
- whether immediate execution is likely;
- post-action state.

### 5. Recovery before pressure — `RECOVERY_GAP`

Recovery should restore a real interrupted intention, not pressure a user into a financial action. Order drafts, failed funding and incomplete KYC require clear state, bounded frequency and a visible exit.

### 6. Evidence before growth claims — `MEASUREMENT_GAP`

Conversion, funding and trading activity must be read beside:

- KYC abandonment and re-upload rate;
- rejected-order rate;
- immediate cancellation or correction rate;
- support contacts after financial actions;
- complaint and harm signals;
- seven-day return;
- successful task completion;
- retention by intent segment.

### 7. Human freedom at every stage — `FRICTION_RISK`

Every journey should retain:

- a visible no or decline path;
- a route back;
- a comprehensible total;
- a way to correct or challenge state;
- a clear distinction between draft, submitted, pending, executed, rejected and cancelled.

## Confirmed public findings

| ID | Severity | Evidence status | Product impact | Repair direction |
|---|---|---|---|---|
| `mobile-chart-user-agent-404` | P1 | `CONFIRMED` | A mobile user loses access to a public analytical capability and receives a generic failure state. | Preserve symbol/context and route to a supported mobile chart or explicit supported-state page. |
| `mobile-hero-late-discovery` | P1-performance | `CONFIRMED` | Meaningful content appears several avoidable seconds late, increasing abandonment and uncertainty. | Expose the selected responsive LCP resource in initial HTML and prioritise only that resource. |
| `terminal-hidden-mobile-asset` | P2 | `CONFIRMED` | Mobile users pay network, battery and time cost for a resource rendered at `0×0`. | Prevent the hidden responsive branch from requesting the asset. |
| `terminal-missing-onboarding-asset` | P3 | `CONFIRMED` | Adds request and diagnostic noise; no visible user break was proven. | Remove or correct the obsolete first-party asset reference. |

## Desktop web recommendations

### D1. Persistent system-state header — `NEEDS_AUTHENTICATED_EVIDENCE`

For every trading surface, persistently display:

```text
REAL or DEMO
market session state
live or delayed data
active account and currency
margin state and buying power
```

**Risk addressed:** users acting on the wrong environment, stale data or misunderstood session state.

### D2. Decision-centred workspace — `HYPOTHESIS`

Organise the terminal around the task sequence:

```text
Discover → Analyse → Trade → Manage
```

The chosen instrument, account, session and data state should survive transitions.

### D3. Complete order preview — `NEEDS_AUTHENTICATED_EVIDENCE`

Before submit, show:

- direction, instrument and quantity;
- order type and limit/stop values;
- estimated execution behaviour;
- estimated total, fee and conversion;
- available balance and estimated remainder;
- market-session implications;
- explicit uncertainty for market orders and gaps.

### D4. Explain marketable limit orders — `NEEDS_AUTHENTICATED_EVIDENCE`

When a buy limit is above the current ask, or a sell limit is below the current bid, explain that the order is likely to execute immediately at the best available price within the limit.

### D5. Explicit order control — `NEEDS_AUTHENTICATED_EVIDENCE`

Use labelled actions such as `Modify` and `Cancel`, not an ambiguous standalone `X`. Show:

```text
active
→ cancellation requested
→ cancellation confirmed or execution won the race
```

### D6. Position protection in context — `NEEDS_AUTHENTICATED_EVIDENCE`

Stop Loss and Take Profit should be visible from the selected position without horizontal searching. A risk preview should express both price distance and approximate financial outcome, with gap/slippage uncertainty.

### D7. Attention queue — `HYPOTHESIS`

Create a decision-oriented block:

- active orders requiring attention;
- positions without protection;
- closed-market consequences;
- insufficient currency or buying power;
- rejected or partially completed actions;
- stale or delayed data.

## Mobile web recommendations

### M1. Do not compress desktop tables — `HYPOTHESIS`

Transform positions and orders into task cards. Critical identity, status and action must fit without horizontal scrolling.

Example:

```text
TSLA.US · Active
BUY · Limit
2 × $310 · Total $620
[Modify] [Cancel]
```

### M2. Four-item primary navigation — `HYPOTHESIS`

A bounded mobile structure:

```text
Home | Search | Portfolio | More
```

Secondary concepts should appear in context rather than as a dense global tab row.

### M3. Dedicated order sheet — `NEEDS_AUTHENTICATED_EVIDENCE`

Use a full-screen sheet or bottom sheet:

```text
instrument
→ direction
→ order type
→ quantity and price
→ preview
→ confirmation
```

Do not place chart, market depth, positions, orders, news and the complete order form into one mobile viewport.

### M4. Sticky action state — `HYPOTHESIS`

Keep price, session state and explicit actions visible. When the market is closed, the CTA should say what happens next, for example `Create order for next session`, not only `Buy`.

### M5. Safe draft recovery — `NEEDS_AUTHENTICATED_EVIDENCE`

After interruption:

- restore the draft, not the old confirmation;
- refresh quote, session and buying power;
- invalidate stale previews;
- require a new review before submit;
- distinguish draft from submitted order.

## Ethical ClickFunnels application

Use funnel patterns to remove uncertainty, not to manufacture urgency.

### Recommended sequence

```text
traffic
→ intent-specific landing page
→ demo or watchlist value
→ minimal account creation
→ activation checklist
→ KYC
→ funding
→ real-order preview
→ first intentional action
→ protection and portfolio understanding
→ return
```

### Recommended entry offers

| Intent | Hook | First value | Primary CTA |
|---|---|---|---|
| New investor | Start without learning the whole terminal first | Three-instrument watchlist and simulated order preview | `Try demo` |
| Active trader | Keep market, data and order consequences in one context | Configured trading workspace | `Open terminal` |
| Returning client | See what requires attention now | Portfolio attention queue | `Open portfolio` |

### Explicit exclusions

Do not use:

- false countdowns or artificial scarcity;
- preselected paid data, margin or risk-increasing options;
- hidden recurring terms;
- obstructed decline or cancellation;
- activity metrics as a substitute for successful user outcomes;
- recovery messages that pressure the user to trade.

## Activation checklist

A first-session checklist should lead to value before commitment:

```text
✓ account created
○ choose your intent
○ add three instruments
○ inspect market and data state
○ create a demo order preview
○ complete KYC when ready
○ choose a funding method
```

The checklist must preserve progress and must not imply that the user should place a real trade before understanding the state and consequences.

## Measurement model

### Primary activation metric

**Qualified seven-day activation:** the share of eligible new users who complete KYC where required, realise the first value for their selected intent, and complete one intentional product action without a preventable correction or support incident.

### Funnel events

```text
landing_view
intent_selected
demo_started
signup_started
signup_completed
activation_step_completed
instrument_searched
instrument_opened
watchlist_item_added
order_form_opened
order_preview_viewed
order_warning_viewed
order_submitted
order_rejected
order_cancel_requested
order_cancel_confirmed
position_protection_opened
stop_loss_created
draft_restored
kyc_started
kyc_completed
account_funded
```

### Guardrails

- immediate order cancellation or correction;
- repeated submit clicks;
- insufficient-funds and currency-mismatch errors;
- support contact after an order or funding attempt;
- KYC re-upload and abandonment;
- confusion between real and demo;
- action attempted on stale preview;
- mobile horizontal scroll before a critical action;
- complaint, refund, churn and harm signals where applicable.

## Prioritised backlog

### P0 — safety, control and broken public value

1. Repair mobile chart routing while preserving symbol/context.
2. Fix late mobile hero discovery.
3. Remove the hidden mobile terminal asset request.
4. Remove or correct the missing onboarding asset.
5. Validate persistent real/demo, market and data state under an authorised account.
6. Validate complete order preview and marketable-limit explanation.
7. Validate explicit cancellation state and race handling.
8. Validate Stop Loss/Take Profit discoverability from a selected position.
9. Validate mobile order cards and draft recovery.

### P1 — activation and comprehension

1. Intent-segmented landing page.
2. Demo-first entry for cold traffic.
3. Activation checklist with preserved progress.
4. Attention queue for orders, positions and data state.
5. Mobile task navigation and dedicated order sheet.
6. Recovery paths for KYC, funding and rejected orders.

### P2 — retention and learning

1. Intent-specific workspace presets.
2. Contextual education at the moment of action.
3. Explain portfolio changes and unresolved attention items.
4. Bounded, opt-out-aware reminders tied to a real unfinished intention.

## Experiment plan

| Experiment | Control | Variant | Primary metric | Guardrails |
|---|---|---|---|---|
| Intent entry | Generic landing | Invest / Trade / Demo split | Meaningful next-step completion | Bounce, wrong-segment backtracking |
| Demo CTA | Open account | Try demo | Demo activation to qualified signup | Low-quality signups, support load |
| Registration choice | All methods equally prominent | One primary method + alternatives | Signup completion | Duplicate accounts, login recovery |
| Order preview | Current flow | Complete consequences preview | Successful intentional submit | Corrections, rejects, support contacts |
| Activation | Direct terminal entry | Preserved checklist | Seven-day qualified activation | Premature real trading, abandonment |
| Mobile orders | Responsive table | Task cards | Successful order-management task | Mis-taps, horizontal scroll, time-to-state |

Every experiment must name:

- exact build and journey;
- cohort and denominator;
- observation window;
- exclusions;
- privacy boundary;
- rollback condition;
- uncertainty;
- accompanying harm and complaint signals.

## Authenticated validation matrix

| Journey | Desktop | Mobile web | Evidence required |
|---|---:|---:|---|
| First login and real/demo comprehension | Required | Required | Video, screenshots, DOM/state log |
| Instrument search and market/data state | Required | Required | State matrix across open/closed/delayed |
| Market order preview | Required | Required | Fee, currency, session and total evidence |
| Marketable limit order | Required | Required | Bid/ask, warning and resulting state |
| Order cancellation race | Required | Required | Request, pending and final server state |
| Stop Loss/Take Profit | Required | Required | Discoverability, preview and final state |
| Insufficient funds/currency | Required | Required | Error cause and recovery options |
| Interrupted mobile draft | Not primary | Required | Draft restore and stale-preview invalidation |
| Reconnect and quote freshness | Required | Required | Market-open timestamps and reconnect trace |

## Definition of done

A recommendation can move from hypothesis to product finding only when:

1. the exact journey, build, account type and environment are recorded;
2. the behaviour is reproducible or its variability is quantified;
3. user impact is demonstrated rather than inferred from a screenshot alone;
4. competing explanations are addressed;
5. evidence is bound to exact artifacts or runs;
6. unknowns remain explicit;
7. the proposed repair has measurable acceptance criteria;
8. no advisory document is treated as approval to deploy, report externally or merge.

## Final product question

> Does the journey help a person realise the intended value while keeping state, price, risk, choice, evidence, recovery and exit visible?

Where the answer is not yet supported, the correct label is not "bad UX". It is `NEEDS_EVIDENCE` with a bounded next test.
