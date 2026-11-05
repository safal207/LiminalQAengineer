# Tradernet product backlog and validation plan

**Companion to:** `TRADERNET_PRODUCT_FUNNEL_AUDIT.md`  
**Backlog version:** `v0.1`  
**Status:** human review required

## Operating rule

A ticket is either:

- a confirmed public finding with exact evidence; or
- a bounded product hypothesis with an explicit validation plan.

Do not convert an authenticated-journey hypothesis into a defect report until the required evidence exists.

## Prioritisation model

| Priority | Meaning |
|---|---|
| `P0` | Broken public value, financial-action ambiguity, state/control risk, or mobile recovery risk. |
| `P1` | Material activation, comprehension or conversion improvement. |
| `P2` | Retention, personalisation or learning improvement after core safety and activation are reliable. |

## P0 backlog

### TN-PROD-001 — Repair mobile public chart routing

- **Status:** `CONFIRMED`
- **Severity:** `P1`
- **Source:** LiminalQA PR `#58`
- **Problem:** mobile user-agents receive the generic 404 experience for the public chart route.
- **User impact:** the analytical task ends without preserving instrument context or explaining a supported alternative.
- **Acceptance criteria:**
  - the tested public symbol opens a supported chart on mobile user-agents;
  - viewport width and user-agent combinations produce a documented supported state;
  - instrument context is preserved through any redirect;
  - no generic 404 is shown for a supported public route;
  - automated matrix covers desktop/mobile user-agents and narrow/wide viewports.
- **Guardrails:** do not silently redirect to an unrelated instrument or authenticated-only surface.

### TN-PROD-002 — Make the mobile hero discoverable in initial HTML

- **Status:** `CONFIRMED`
- **Severity:** `P1-performance`
- **Source:** LiminalQA PR `#54`
- **Problem:** late discovery of the selected mobile hero materially delays LCP.
- **Acceptance criteria:**
  - the selected mobile LCP resource is discoverable from initial HTML;
  - only the selected responsive hero is prioritised;
  - three alternating baseline/variant rounds show a material median improvement;
  - CLS does not regress;
  - desktop resource scheduling does not regress.
- **Guardrails:** compare medians and retain raw artifacts; do not claim production impact from one run.

### TN-PROD-003 — Stop downloading the hidden mobile terminal asset

- **Status:** `CONFIRMED`
- **Severity:** `P2`
- **Source:** LiminalQA PR `#60`
- **Problem:** a `346,800` byte image is downloaded and rendered at `0×0`.
- **Acceptance criteria:**
  - the hidden branch does not initiate the request;
  - no equivalent duplicate asset replaces it;
  - terminal entry remains visually complete;
  - mobile transfer size decreases by the expected bounded amount;
  - automated visibility probe passes.

### TN-PROD-004 — Remove the missing onboarding asset request

- **Status:** `CONFIRMED`
- **Severity:** `P3`
- **Source:** LiminalQA PR `#60`
- **Problem:** terminal entry requests a missing first-party onboarding asset.
- **Acceptance criteria:**
  - the obsolete reference is removed or points to a valid intentional asset;
  - no first-party 404 occurs on terminal entry;
  - the product does not introduce a new visible layout gap;
  - browser-console and network assertions remain green.

### TN-PROD-005 — Persist real/demo, session and data state

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Risk:** financial-action state ambiguity
- **Hypothesis:** every trading surface should persistently expose real/demo, market session, live/delayed data, active account/currency, margin state and buying power.
- **Validation matrix:**
  - real and demo accounts;
  - market open, premarket, after-hours and closed;
  - live, delayed and unavailable data;
  - desktop and mobile web;
  - reconnect and stale-data conditions.
- **Acceptance criteria after validation:**
  - the state is visible before any actionable control;
  - state changes are announced without relying on colour alone;
  - stale or unavailable data disables or qualifies affected actions;
  - the selected account and currency survive navigation;
  - screenshots and state logs are bound to the exact build.

### TN-PROD-006 — Add complete order consequences preview

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Risk:** misunderstood financial commitment
- **Required preview:**
  - instrument and direction;
  - quantity and order type;
  - limit/stop values;
  - expected execution behaviour;
  - estimated price, fee, currency conversion and total;
  - available balance and estimated remainder;
  - market-session consequence;
  - uncertainty for market orders, gaps and slippage.
- **Acceptance criteria after validation:**
  - user can explain what will happen before submit;
  - changing quantity, price, account or currency refreshes the preview;
  - stale previews are invalidated;
  - insufficient-funds states provide cause and bounded recovery choices;
  - no fee or conversion appears only after commitment.

### TN-PROD-007 — Explain marketable limit orders

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Risk:** user expects a waiting order that may execute immediately
- **Trigger:** buy limit above current ask or sell limit below current bid.
- **Acceptance criteria after validation:**
  - warning names current bid/ask and entered limit;
  - wording explains likely immediate execution within the limit;
  - warning refreshes when the market moves materially;
  - delayed quotes are labelled;
  - user can return to edit without losing context.

### TN-PROD-008 — Make cancellation explicit and stateful

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Risk:** ambiguous control and false certainty
- **Acceptance criteria after validation:**
  - action is labelled `Cancel`, not only represented by `X`;
  - confirmation names instrument, direction, quantity and price;
  - UI distinguishes cancellation requested from cancellation confirmed;
  - execution-won-the-race state is handled explicitly;
  - repeated clicks do not create duplicate cancellation requests;
  - desktop and mobile state transitions are captured.

### TN-PROD-009 — Put Stop Loss and Take Profit in position context

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Risk:** protection is difficult to discover or understand
- **Acceptance criteria after validation:**
  - protection actions are visible from the selected position;
  - no horizontal search is required on mobile;
  - preview shows price distance and approximate financial outcome;
  - gap/slippage uncertainty is explicit;
  - created, modified, rejected and cancelled states are visible;
  - task success and comprehension are measured with representative users.

### TN-PROD-010 — Replace mobile management tables with task cards

- **Status:** `HYPOTHESIS`
- **Risk:** critical identity, state or action falls outside the viewport
- **Variant:** position and order cards containing symbol, direction, type, quantity, price/total, state and explicit actions.
- **Experiment metrics:**
  - task completion;
  - time to find active order;
  - cancellation error rate;
  - horizontal-scroll distance;
  - mis-taps;
  - return-to-context rate.
- **Guardrails:** cards must not hide partial fills, rejected state or currency.

### TN-PROD-011 — Restore mobile drafts safely

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Risk:** old state is mistaken for a current confirmation
- **Acceptance criteria after validation:**
  - draft input survives interruption;
  - prior confirmation does not survive as valid;
  - quote, session, fee, buying power and total refresh on return;
  - stale preview requires a new review;
  - draft, submitted and pending states are visually distinct;
  - reconnect trace proves which server state is authoritative.

## P1 backlog

### TN-PROD-101 — Segment entry by intent

- **Status:** `HYPOTHESIS`
- **Variants:** `Start investing`, `Active trading`, `Try demo`.
- **Primary metric:** meaningful next-step completion by intent.
- **Secondary metrics:** qualified signup, activation, KYC completion, seven-day return.
- **Guardrails:** wrong-segment backtracking, support contacts and premature real trading.

### TN-PROD-102 — Create a demo-first cold-traffic path

- **Status:** `HYPOTHESIS`
- **First value:** three-instrument watchlist plus simulated order preview.
- **Primary metric:** demo activation to qualified signup.
- **Guardrails:** low-intent account creation, misleading simulation, pressure to fund or trade.

### TN-PROD-103 — Add a preserved activation checklist

- **Status:** `HYPOTHESIS`
- **Suggested steps:**
  - choose intent;
  - add three instruments;
  - inspect market/data state;
  - create demo preview;
  - complete KYC when ready;
  - choose funding method.
- **Acceptance criteria:** progress persists, the checklist can be dismissed, and no step implies that real trading is mandatory.

### TN-PROD-104 — Add a portfolio attention queue

- **Status:** `HYPOTHESIS`
- **Candidate items:** active orders, positions without protection, closed-market consequences, insufficient currency, rejected actions and stale data.
- **Primary metric:** successful resolution of a real attention item.
- **Guardrails:** no alarmist language and no recommendation to trade without user intent.

### TN-PROD-105 — Use bounded mobile navigation

- **Status:** `HYPOTHESIS`
- **Candidate primary navigation:** `Home | Search | Portfolio | More`.
- **Acceptance criteria:** core tasks are reachable without competing global tab rows; selected instrument and state persist.

### TN-PROD-106 — Build recovery for KYC, funding and rejected orders

- **Status:** `NEEDS_AUTHENTICATED_EVIDENCE`
- **Required pattern:** cause, exact state, user-correctable field, example where useful, retry path, exit path and saved progress.
- **Guardrails:** bounded recovery frequency, privacy protection and no pressure to continue.

## P2 backlog

### TN-PROD-201 — Intent-specific workspace presets

- New investor: watchlist, simple chart, state explanation and demo preview.
- Long-term investor: allocation, change explanation and attention queue.
- Active trader: chart, depth, positions, orders and consequences preview.

### TN-PROD-202 — Contextual education at the moment of action

Explain limit behaviour, session state, delayed data, fee/conversion and protection only when relevant. Avoid a generic tutorial wall.

### TN-PROD-203 — Explain portfolio change

Separate price movement, deposits/withdrawals, fees, realised result, unrealised result and currency effects.

### TN-PROD-204 — Bounded recovery reminders

Remind only for a real unfinished intention. Preserve opt-out, frequency cap, privacy and stop condition. Never use artificial urgency to induce trading.

## Analytics contract

### Required events

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

### Required dimensions

- intent segment;
- desktop/mobile web;
- real/demo;
- market session;
- live/delayed/unavailable data;
- account currency;
- order type;
- new/returning user;
- experiment and variant;
- exact build.

### Privacy boundary

Do not place private portfolio values, document data, credentials or raw personal identifiers into public analytics or audit artifacts.

## Human-review checklist

Before converting a backlog item into an external report or implementation decision:

- [ ] Exact build, environment and account type are recorded.
- [ ] Evidence label is correct.
- [ ] Confirmed behaviour and product hypothesis are separate.
- [ ] User impact is demonstrated.
- [ ] Competing explanations are addressed.
- [ ] Acceptance criteria are measurable.
- [ ] Guardrails include complaints and harm signals where relevant.
- [ ] No ClickFunnels pattern introduces false urgency or hidden commitment.
- [ ] No audit label is treated as approval, delivery or merge authority.
