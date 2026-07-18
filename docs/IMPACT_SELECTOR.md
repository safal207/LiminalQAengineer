# LiminalQA Impact Selector MVP

## Purpose

The Impact Selector reduces feedback time by choosing a bounded, explainable subset of tests before `TestRunner` starts execution.

```text
changed repository paths
→ deterministic impact rules
→ risk-ranked test plan
→ TestRunner adaptive execution
→ Council signal reconciliation
→ Reflection
```

The selector does not execute tests, approve merges, or replace human QA judgment. It produces an advisory execution plan.

## Inputs

- changed repository paths;
- a test catalog;
- path-to-test impact rules;
- business criticality;
- recent failure rate;
- flake probability;
- expected duration;
- smoke-fallback eligibility.

## Rules

The MVP supports three deterministic rule types:

- `PathPrefix`: strongest relationship;
- `PathContains`: medium-strength relationship;
- `Extension`: broad language/file-type relationship.

Each selected test includes the exact changed path and rule that caused the match.

## Risk model

For directly matched tests:

```text
60% strongest path match
20% business criticality
15% recent failure rate
 5% detector reliability (1 - flake probability)
```

The score is normalized to `0..100` and is used only for ordering and thresholding.

## Safe fallback

When no test has a direct impact match, the selector returns a bounded set of smoke tests instead of silently returning an empty plan.

The fallback is visible in the output:

```json
{
  "fallback_used": true
}
```

## Determinism

Plans are sorted by:

1. risk score descending;
2. expected duration ascending;
3. suite;
4. test name.

The same inputs produce the same plan.

## Example

```bash
cargo run -p liminalqa-runner --example impact_selector
```

The example models changes in authentication and session code. The selector chooses only connected auth/session tests and omits unrelated trading tests.

## Next steps

- ingest changed paths directly from a Git diff;
- persist test-to-component edges in LiminalDB;
- learn historical edges from confirmed regressions without hiding their evidence;
- execute the plan with bounded Tokio concurrency;
- compare estimated duration with full-suite duration;
- add exact commit SHA and catalog digest to the selection packet.
