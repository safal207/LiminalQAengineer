---
name: product-impact
description: Translate supported defects into user, trust, conversion, support, operational, and financial impact without presenting unmeasured business loss as fact. Use after causal adjudication.
---

# Product Impact

## Objective

Explain why a supported finding matters in the real journey, while keeping measured facts, modeled scenarios, and unknowns separate.

## Impact chain

```text
technical or content condition
-> visible user state
-> user interpretation
-> behavior change
-> journey outcome
-> business or operational consequence
```

Every arrow needs evidence or an explicit hypothesis label.

## User-impact lenses

Assess the applicable dimensions:

- goal completion;
- time and cognitive load;
- error prevention;
- control and reversibility;
- visibility of system status;
- accessibility and reachability;
- trust and credibility;
- privacy and perceived safety;
- recovery after failure;
- consistency across time, device, locale, and session.

## Business-impact lenses

Assess:

- acquisition and first-use conversion;
- activation and task completion;
- retention and repeat use;
- support contacts and manual handling;
- operational rework;
- compliance or governance exposure;
- brand and partner trust;
- engineering opportunity cost;
- revenue or margin risk.

## Evidence classes

For every impact statement, choose one:

- `MEASURED` — supported by analytics, experiments, tickets, logs, or financial data;
- `MODELED` — calculated from explicit assumptions and ranges;
- `QUALITATIVE` — supported by the journey and human-factors reasoning, without a numeric estimate;
- `UNKNOWN` — data is missing.

Do not convert `MODELED` or `QUALITATIVE` into a factual loss number.

## Scenario model

When useful, estimate a range:

```text
eligible users
x exposure rate
x affected-step rate
x incremental abandonment or rework
x value per completed outcome
= modeled impact range
```

List every assumption, use low/base/high scenarios, and identify the metric that would falsify the model.

## Prioritization

Rank findings using separate dimensions:

- user harm;
- business exposure;
- evidence confidence;
- affected population;
- recurrence;
- recoverability;
- remediation cost;
- learning value.

Do not let a dramatic but weakly evidenced finding automatically outrank a smaller confirmed defect on a critical journey.

## Output per finding

Return:

- affected user goal;
- visible friction or risk;
- likely behavior response;
- journey and business consequence;
- evidence class;
- assumptions and uncertainty;
- measurement plan;
- cheapest high-value experiment or fix candidate;
- success metric and guardrail metric.

Recommendations remain hypotheses until implementation and measurement confirm them.
