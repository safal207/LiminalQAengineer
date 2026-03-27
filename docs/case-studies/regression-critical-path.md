# Case Study 2: Catching a Regression Before Production

**Scenario**: SaaS platform, authentication service, 5-engineer team
**Test suite**: ~200 tests on the auth service, deploy 3–4 times per week
**Stakes**: `auth/verify_token` guards every authenticated endpoint

---

## The situation

On a Wednesday afternoon, a routine PR to refactor token validation logic
passed all checks and was merged.  The engineer saw `charge_card` fail once
in CI, re-ran it, it passed — and pushed through.

Six hours later, 8% of API calls were returning 401.  Not a flaky test.
A real regression.

The post-mortem question: could this have been caught before merge?

The answer with LiminalQA: yes, in under 2 seconds.

---

## What the CI saw (before LiminalQA)

```
❌ auth/verify_token — FAILED (timeout 2000ms)
   Retrying... ❌ FAILED
   Retrying... ❌ FAILED

Test suite: 3/200 failed
Overall: ❌
```

Three questions the engineer had to answer manually:
1. Is this a known flake on `verify_token`? *(not sure — it's usually stable)*
2. Is the timeout relevant? *(maybe infra, maybe the refactor broke something)*
3. Should I block or merge? *(coin flip)*

They merged.

---

## What LiminalQA would have shown

```
╔════════════════════════════════════════════════════════════════════╗
║  LIMINALQA · auth/verify_token                                     ║
╚════════════════════════════════════════════════════════════════════╝

┌─ A  TEST RISK CARD ────────────────────────────────────────────────┐
│  verdict:        ⚠ NEW_BUG              confidence:  74%           │
│  severity:       CRITICAL               merge:  🔴 BLOCK            │
│  action:         block_and_alert        trend:  ↗ degrading        │
│  flake risk:     █░░░░░░░░░░░░░░░░░░░ 5%                           │
│  insight:        Test was stable (99% pass rate) but failed in…    │
└────────────────────────────────────────────────────────────────────┘

┌─ B  ROOT CAUSE ANALYSIS ───────────────────────────────────────────┐
│  most likely:    code_regression (55%)                              │
│                                                                     │
│  ▶ code_regression           █████████░░░░░░░░░  55%               │
│    · triage verdict: new_bug (stable → failing)                     │
│    · high failure rate (90%) with low flake probability (5%)        │
│    · failure in production environment                              │
│  ▶ infrastructure_flake      ██░░░░░░░░░░░░░░░░  15%               │
│  ▶ external_dependency       ██░░░░░░░░░░░░░░░░  15%               │
│    · high-load context (1.5× multiplier)                            │
│                                                                     │
│  fix:  Bisect recent commits; review changes to code paths…         │
└────────────────────────────────────────────────────────────────────┘

┌─ C  WHAT-IF  /  COUNTERFACTUAL ────────────────────────────────────┐
│  current pass rate    █░░░░░░░░░░░░░░░░░░░  9%                      │
│                                                                     │
│  if code regression fixed  ████░░░░░░░░░░░░░░░░  20%  (+11pp)       │
│    → partial: investigate token validation refactor                 │
│  if external dep fixed     ████████████████░░░░  80%  (+71pp)       │
│    → if root cause is upstream: check JWT lib / DB session store    │
└────────────────────────────────────────────────────────────────────┘

┌─ D  COMMUNITY INSIGHTS ────────────────────────────────────────────┐
│  matches:  similar regression pattern in community knowledge base   │
│                                                                     │
│  ▶ similarity 99%   seen in 4 project(s)                            │
│    action:  Bisect recent commits — likely real regression           │
│    effective: 50%+ of reporters resolved with this action           │
└────────────────────────────────────────────────────────────────────┘
```

The GitHub Action bot would have posted this to the PR before any human
reviewed it:

```
🔴 LiminalQA: MERGE BLOCKED

auth/verify_token — NEW_BUG detected (confidence: 74%)

Most likely cause: code_regression (55%)
· Test was stable (99% pass rate over 25 runs) but failed in 3 consecutive runs
· High failure rate (90%) with low flake probability (5%) — not a flake

Suggested action: bisect recent commits; review changes to token
validation code paths covered by this test.

Merge policy: BLOCK — confirmed regression, not a known flake.
```

---

## The difference

| | Without LiminalQA | With LiminalQA |
|---|---|---|
| Time to verdict | ~40 min (post-mortem) | < 2 sec (pre-merge) |
| Merge decision | "retry passed, ship it" | `🔴 BLOCK` — automated |
| Root cause hint | discovered 6h later | in PR comment |
| Customer impact | 8% of API calls returning 401 | zero |
| Incident writeup | yes | no |

---

## Why the difference matters

The test failed three times in a row.  Flake probability: 5%.
It had a 99% pass rate over 25 runs.

That combination — *stable history + sudden consistent failure + low flake
probability* — is the textbook signature of `new_bug`.

A human looking at a single CI log can't see 25 runs of history.  LiminalQA
can.  And it can see it in the same time it takes the PR to open.

The confidence was 74% — not 100%.  LiminalQA doesn't pretend to be certain.
But 74% confidence with a `CRITICAL` severity and a `🔴 BLOCK` policy is
enough to pause for 5 minutes and check the diff before merging something
that guards every authenticated endpoint.

---

## The lesson

The regression was not subtle.  The signal was there.
The problem was that the signal required *pattern recognition across history* —
the kind of thing humans do poorly under deadline pressure and machines do
trivially.

LiminalQA's value in this scenario isn't algorithmic genius.
It's the fact that it *looks at history automatically and tells you what it sees*,
before you make the decision that's hardest to undo.

---

## What to do if you see `🔴 BLOCK`

1. Don't panic — it's a hypothesis, not a certainty (confidence shown)
2. Look at the evidence in Panel B — is it pointing at something real?
3. Check Panel C — if fixing the regression raises pass rate to 80%+, the
   signal is strong
4. Look at the recent diff — specifically the code paths this test covers
5. If you want to override: explicitly annotate the PR ("known issue: #123")

The goal is 5 minutes of deliberate review, not blind deference to automation.

---

## Takeaway

If you have a test that:
- Has been stable for weeks (≥ 90% pass rate)
- Suddenly fails 3 times in a row
- And the failures are not obviously infra-related

...LiminalQA will classify it as `new_bug`, block the merge with a `CRITICAL`
severity, and tell you exactly which hypothesis to investigate first.

```bash
# See it yourself:
cargo test -p liminalqa-core --test dashboard_demo \
  -- scenario_new_regression --nocapture
```

---

*Previous: [Case Study 1 — Flaky CI Bottleneck](./flaky-ci-bottleneck.md)*
