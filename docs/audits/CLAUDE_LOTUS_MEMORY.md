# Claude → Lotus → LiminalDB Memory Integration v0.2

## Purpose

This integration combines the exact passive Claude public-web portfolio evidence from workflow run `29665084768` with the exact Claude Code DevTools-throttled rerun from workflow run `29666017830`, feeds both through the Lotus judgment contract, and writes the resulting state into the replayable LiminalDB-compatible ledger.

It preserves four boundaries:

1. OpenAI and Claude findings keep separate canonical IDs and evidence lineages.
2. A shared contributor does not become one root cause across unrelated runtimes.
3. Missing Lighthouse metrics do not become a confirmed severity claim.
4. Superseding evidence adds a new event and does not delete the earlier conflict.

## Exact Claude portfolio evidence

- benchmark PR: `#62`
- evidence head: `df79bc0f6330b6430fcb3c29962c293697158037`
- workflow run: `29665084768`
- portfolio artifact SHA-256: `bc084810a9a1a5ef48cfe4d3eb6186dcc176e728761f376165cd2b07eda8a117`

## Exact Claude Code rerun evidence

- experiment PR: `#68`
- exact evidence head: `fab4cd94d237628b57abac6e74049c1c13c57756`
- workflow run: `29666017830`
- artifact SHA-256: `f281d9d0787d0e5d9565d9f42d7677a586f739a8f89cd1ae556d9a1f954d1682`
- result SHA-256: `79e1089146aa66a2beef0e8daf069191424ff211498877db9bc0e9f9cc1dcaf9`

Profile:

- three sequential passive navigations;
- mobile `390x844`, DPR `1`;
- DevTools throttling;
- RTT `150 ms`;
- throughput `1638.4 Kbps`;
- CPU slowdown `4x`.

Result:

- valid LCP: `3/3`;
- NO_LCP: `0/3`;
- median Performance: `35`;
- median LCP: `7.299 s`;
- median TBT: `2.294 s`;
- LCP range: `6.463–7.588 s`.

## Claude Lotus findings

### Confirmed bounded findings

- `CLAUDE-PUBLIC-SHELL-PERFORMANCE-001`
  - LCP `33.92 s`
  - TBT `3.99 s`
  - estimated unused JavaScript `2,936 KiB`

- `CLAUDE-PRODUCT-OVERVIEW-PERFORMANCE-001`
  - LCP `41.43 s`
  - Accessibility `73`
  - render-blocking opportunity `2.43 s`

- `CLAUDE-CODE-DEVTOOLS-PERFORMANCE-001`
  - `3/3` valid LCP measurements
  - median Performance `35`
  - median LCP `7.299 s`
  - median TBT `2.294 s`
  - `ALLOW / PROPOSED_RECURRING / MEDIUM / CONFIRMED`
  - supersedes the earlier `NO_LCP` only as current measurement state

- `CLAUDE-SHARED-JS-CONTRIBUTOR-001`
  - unused JavaScript recurs in `6/7` portfolio packets
  - boot-time and bfcache findings recur in `5/7`
  - classified as a contributor pattern, not one universal root cause

- `CLAUDE-STATUS-INSPECTABILITY-001`
  - Accessibility `83`
  - Best Practices `79`
  - bounded contrast and semantic findings

### Historical conflict retained

- `CLAUDE-CODE-PERFORMANCE-ZERO-001`
  - the original packet displayed Performance `0`;
  - LCP and TBT were null;
  - Lighthouse emitted `NO_LCP`;
  - the zero remains invalid as a product score;
  - Lotus retains `ESCALATE / CONFLICT / NEEDS_EVIDENCE` as historical measurement evidence.

The new exact finding does not rewrite the old event. Both remain replayable in the ledger.

## Combined packet

The merger combines the original seven cross-domain findings, five portfolio Claude findings, and one exact Claude Code rerun finding:

```text
7 existing findings
+ 5 Claude portfolio findings
+ 1 Claude Code superseding finding
= 13 Lotus findings
= 65 LiminalDB ledger events
```

Expected decisions:

```text
Pythia: 10 ALLOW / 1 BLOCK / 2 ESCALATE
Unified: 10 CONFIRMED / 1 BLOCKED / 2 NEEDS_EVIDENCE
CML durable accepted memories: 0
```

Exact combined evidence from workflow run `29666212799`:

- packet SHA-256: `ccea168e6ffd7e62054b97378d957b97a55bad4b5489860bf3ac47b4beb9f766`;
- ledger head: `80a88fae1fdb4903450e1fe14821e410bb5e5487438fd5c36c29e7320627e7fa`;
- snapshot SHA-256: `8336dbaaefc9b291b6d02fd8f98487d073d73cc1d54bd1fe08a8c24a853737bf`;
- artifact SHA-256: `07c2ea0c5548b09efce71847c00edacf4dc5a2da2d70278762306e8a7cae0942`.

## Replay contract

CI:

1. validates all three findings documents;
2. merges them deterministically;
3. rejects duplicate finding IDs or repository drift;
4. regenerates the Lotus Decision Packet;
5. verifies the old conflict and new superseding finding independently;
6. generates a 65-event SHA-linked ledger;
7. replays the ledger into a snapshot;
8. regenerates everything a second time and compares outputs byte-for-byte;
9. uploads the combined evidence artifact.

## Authority boundary

This remains an audit-only integration.

- no live LiminalDB network write;
- no Anthropic authentication;
- no prompts or model calls;
- no API calls;
- no external ticket creation;
- no deployment or merge authority;
- no durable CML memory acceptance without explicit human review.
