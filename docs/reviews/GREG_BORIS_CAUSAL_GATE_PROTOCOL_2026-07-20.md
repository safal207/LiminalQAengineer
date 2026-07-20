# Greg and Boris pre-notification causal gate

Date: 2026-07-20

No external report is sent until the evidence passes four independent dimensions.

## 1. Space

Every claim must resolve to an exact public coordinate:

- repository;
- issue or pull request number;
- exact source or merge SHA;
- runtime context when execution evidence is used.

A similarly named issue, a fork-local PR, and its upstream PR are separate spaces and cannot be treated as the same object without an explicit identity edge.

## 2. Transition

Every recommendation must identify a real before/after transition.

### Greg

```text
exact tee-output source
→ write unique stdout/stderr records
→ immediate close
→ verify persisted records
```

Counterfactual:

```text
same source and records
→ change shutdown order only
→ flush
→ restore descriptors
→ close writers to deliver EOF
→ wait naturally
→ terminate only on timeout
→ verify persisted records
```

A causal defect claim is permitted only when at least one baseline round loses data and every bounded counterfactual round passes.

### Boris openclaw PRs

```text
fork-local PR remains open
→ same author and title found upstream
→ upstream PR is merged at the expected merge SHA
→ later upstream commit narrows overstated comments
→ lifecycle verdict: superseded, not awaiting review
```

### Boris Claude Code issues

```text
public issue exists
→ issue remains open
→ Boris remains assigned
→ recommendation is expressed as future acceptance or reproduction work
```

The gate does not convert a public report into a confirmed implementation defect without runtime or source evidence.

## 3. Time

The gate checks:

- exact source revision time;
- upstream merge times;
- correction commit time;
- current public issue/PR observation time;
- maximum evidence age before notification.

A stale observation blocks sending even when the earlier conclusion was correct.

## 4. Causality

Allowed conclusions are mechanically derived from result contents.

### Greg

| Evidence | Allowed external classification |
|---|---|
| baseline loss + counterfactual passes | `CONFIRMED_SHUTDOWN_DATA_LOSS_WITH_PASSING_COUNTERFACTUAL` |
| baseline passes + counterfactual passes | `NOT_REPRODUCED_ON_THIS_RUN_STATIC_RISK_REMAINS` |
| counterfactual fails or evidence incomplete | `BLOCKED_DO_NOT_NOTIFY` |

### Boris

| Evidence | Allowed external classification |
|---|---|
| fork open + matching upstream PR merged | `CLOSE_AS_SUPERSEDED` recommendation only |
| issue open and assigned | review/acceptance recommendation only |
| state mismatch or stale observation | `BLOCKED_DO_NOT_NOTIFY` |

## Forbidden overclaims

The reports must not claim:

- every environment is affected;
- production data was lost;
- the Greg counterfactual is a complete production patch;
- the openclaw fixes preserve the entire prompt prefix;
- MCP sorting eliminates order-dependent collision assignment;
- Claude Code issue #4937 is implemented without current CLI verification;
- Claude Code issue #1554 is fixed without current-version reproduction;
- any authority to approve, close, assign, merge, or remediate third-party work.

## Machine gate

Workflow:

```text
.github/workflows/greg-boris-causal-evidence.yml
```

Validator:

```text
scripts/validate_greg_boris_causal_graph.py
```

Possible final verdicts:

```text
READY_TO_NOTIFY_CONFIRMED_GREG_AND_VERIFIED_BORIS
READY_TO_NOTIFY_BORIS_GREG_NONREPRO_ONLY
BLOCKED_DO_NOT_NOTIFY
```

Only the first two permit an external comment. Neither permits changing third-party state.
