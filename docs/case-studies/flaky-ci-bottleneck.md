# Case Study 1: Taming a Flaky Payment Test

**Scenario**: E-commerce platform, payments service, 8-engineer team
**Test suite**: ~400 tests, CI on every PR, average pipeline time 14 minutes
**Problem duration**: 3 months of recurring pain before LiminalQA

---

## The situation

`payments/charge_card` was the team's most-feared test.

It failed roughly 30% of the time — not because the payment logic was broken,
but because the test talked to a staging Stripe mock that occasionally timed out
under load.  No one was sure, though.  Every time it failed, the on-call
engineer had to make a judgment call: real bug or flake?  Retry or block?

The investigation routine had become ritual:

1. CI shows red on `charge_card`
2. Engineer opens logs — sees a network timeout, maybe
3. Manually re-runs the test — it passes
4. Concludes "probably a flake", merges
5. Some weeks it was right.  Some weeks it wasn't.

**Average time per incident**: 25–40 minutes
**False blocks per week**: 3–5 (real deploys held up for non-bugs)
**False clears per month**: 1–2 (actual regressions let through)

---

## What LiminalQA saw

After connecting to the CI pipeline, LiminalQA analysed 30 runs of the test:

```
cargo test -p liminalqa-core --test dashboard_demo -- scenario_flaky_network_test --nocapture
```

```
╔════════════════════════════════════════════════════════════════════╗
║  LIMINALQA · payments/charge_card                                  ║
╚════════════════════════════════════════════════════════════════════╝

┌─ A  TEST RISK CARD ────────────────────────────────────────────────┐
│  verdict:        ⚠ FLAKE                confidence:  80%           │
│  severity:       HIGH                   merge:  🟡 WARN             │
│  action:         retry_with_backoff     trend:  ↗ degrading        │
│  flake risk:     ████████████████░░░░ 82%                          │
│  timeout:        0.7s (EMA mean + 3σ)                              │
│  insight:        Test oscillates between pass and fail (70% stab…  │
└────────────────────────────────────────────────────────────────────┘

┌─ B  ROOT CAUSE ANALYSIS ───────────────────────────────────────────┐
│  most likely:    infrastructure_flake (44%)                         │
│                                                                     │
│  ▶ infrastructure_flake      ███████░░░░░░░░░░░  44%               │
│    · high flake probability (82%)                                   │
│    · triage verdict: flake                                          │
│    · test involves network calls (common flake source)              │
│  ▶ code_regression           ███░░░░░░░░░░░░░░░  19%               │
│    · duration trending up (+9.2 ms/run)                             │
│  ▶ external_dependency       ███░░░░░░░░░░░░░░░  17%               │
│    · network calls present; 30% failure rate                        │
│                                                                     │
│  fix:  Add retry logic with exponential backoff; investigate…       │
└────────────────────────────────────────────────────────────────────┘

┌─ C  WHAT-IF  /  COUNTERFACTUAL ────────────────────────────────────┐
│  current pass rate    ██████████████░░░░░░  70%                     │
│                                                                     │
│  if infra flake fixed      ██████████████████░░  94%  (+24pp)       │
│  if code regression fixed  ████████████████░░░░  80%  (+10pp)       │
│  if external dep fixed     ████████████████░░░░  80%  (+10pp)       │
└────────────────────────────────────────────────────────────────────┘

┌─ D  COMMUNITY INSIGHTS ────────────────────────────────────────────┐
│  matches:  similar incidents in community knowledge base            │
│                                                                     │
│  ▶ similarity 99%   seen in 4 project(s)                            │
│    action:  Add retry with exponential backoff                      │
│    effective: 50%+ of reporters resolved with this action           │
└────────────────────────────────────────────────────────────────────┘
```

In under 2 seconds LiminalQA produced what previously took 25–40 minutes to
determine manually:

- **Verdict**: flake, not a real bug — confidence 80%
- **Why**: 82% flake probability, network calls, oscillating pass/fail pattern
- **What to do**: `retry_with_backoff` — don't block the merge
- **Biggest gain**: fixing the infra issue would bring pass rate from 70% → 94%
  — a concrete target for the sprint backlog

The merge policy came back as `🟡 WARN` — not `🔴 BLOCK`.  The GitHub Action
bot automatically added an annotation to the PR instead of blocking it.

---

## What changed

The team added three things in one afternoon:

**1. Retry policy** (30 minutes)
```yaml
# In test config
charge_card:
  retry:
    strategy: exponential_backoff
    max_retries: 3
    initial_delay_ms: 500
```

**2. LiminalQA GitHub Action** (10 minutes)
```yaml
- name: Ingest test results
  run: |
    curl -X POST "$LIMINALQA_URL/ingest/batch" \
      -H "Authorization: Bearer $LIMINALQA_TOKEN" \
      -d @test-results.json
```

**3. PR annotation bot** (20 minutes)
```python
decision = get_test_decision("payments/charge_card")
if decision["merge_policy"] == "allow_with_warning":
    add_pr_comment(decision["root_cause_hints"])
```

---

## Before and after

| Metric | Before | After |
|--------|--------|-------|
| Time to diagnose `charge_card` failure | 25–40 min | < 2 min |
| False merge blocks per week | 3–5 | 0–1 |
| False clears (regressions let through) | 1–2/month | 0/month |
| Engineer confidence in merge decision | "gut feel" | 80% confidence score |
| Adaptive timeout for the test | 2s (from README) | 0.7s (EMA mean + 3σ) |
| CI time after retry policy added | 14 min | 11.5 min (fewer re-runs) |

---

## The key insight

The team wasn't bad at debugging.  They were spending mental energy on a
decision that a machine can make better — because the machine has 30 runs of
history, knows the statistical pattern, and has seen how other teams handled
the same signature.

**LiminalQA didn't fix the flake.  It made the flake legible.**

Once the root cause was clear (infra, not code), the team could make a
deliberate product decision: live with the flake + retry, or invest a sprint
in stabilising the staging Stripe mock.  They chose the former.  That's the
right call — and they made it in 2 minutes instead of debating it for a week.

---

## Takeaway for your team

If you have a test that:
- Fails intermittently (< 90% pass rate)
- Always passes on manual re-run
- Generates "should I retry this?" conversations on Slack

...LiminalQA will give you a verdict in under 2 seconds, with confidence score,
root cause ranking, and a concrete fix recommendation.

```bash
# See it yourself:
cargo test -p liminalqa-core --test dashboard_demo \
  -- scenario_flaky_network_test --nocapture
```

---

*Next: [Case Study 2 — Real Regression on Critical Path](./regression-critical-path.md)*
