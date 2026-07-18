# Claude → Lotus → LiminalDB Memory Integration v0.1

## Purpose

This integration takes the exact passive Claude public-web evidence from workflow run `29665084768` and feeds it through the existing Lotus judgment contract before writing it into the replayable LiminalDB-compatible ledger.

It preserves three boundaries:

1. OpenAI and Claude findings keep separate canonical IDs and evidence lineages.
2. A shared contributor does not become one root cause across unrelated runtimes.
3. Missing Lighthouse metrics do not become a confirmed severity claim.

## Exact Claude evidence

- benchmark PR: `#62`
- evidence head: `df79bc0f6330b6430fcb3c29962c293697158037`
- workflow run: `29665084768`
- portfolio artifact SHA-256: `bc084810a9a1a5ef48cfe4d3eb6186dcc176e728761f376165cd2b07eda8a117`

## Added Lotus findings

### Confirmed bounded findings

- `CLAUDE-PUBLIC-SHELL-PERFORMANCE-001`
  - LCP `33.92 s`
  - TBT `3.99 s`
  - estimated unused JavaScript `2,936 KiB`

- `CLAUDE-PRODUCT-OVERVIEW-PERFORMANCE-001`
  - LCP `41.43 s`
  - Accessibility `73`
  - render-blocking opportunity `2.43 s`

- `CLAUDE-SHARED-JS-CONTRIBUTOR-001`
  - unused JavaScript recurs in `6/7` packets
  - boot-time and bfcache findings recur in `5/7`
  - classified as a contributor pattern, not one universal root cause

- `CLAUDE-STATUS-INSPECTABILITY-001`
  - Accessibility `83`
  - Best Practices `79`
  - bounded contrast and semantic findings

### Needs evidence

- `CLAUDE-CODE-PERFORMANCE-ZERO-001`
  - the packet reports Performance `0`
  - LCP and TBT are null
  - Lighthouse emitted `NO_LCP`
  - Lotus therefore returns `ESCALATE / CONFLICT / NEEDS_EVIDENCE`

## Combined packet

The merger combines the original seven cross-domain findings with five Claude findings:

```text
7 existing findings
+ 5 Claude findings
= 12 Lotus findings
= 60 LiminalDB ledger events
```

Expected decisions:

```text
Pythia: 9 ALLOW / 1 BLOCK / 2 ESCALATE
Unified: 9 CONFIRMED / 1 BLOCKED / 2 NEEDS_EVIDENCE
CML durable accepted memories: 0
```

## Replay contract

CI:

1. validates both findings documents;
2. merges them deterministically;
3. rejects duplicate finding IDs or repository drift;
4. regenerates the Lotus Decision Packet;
5. generates a 60-event SHA-linked ledger;
6. replays the ledger into a snapshot;
7. regenerates everything a second time and compares outputs byte-for-byte;
8. uploads the combined evidence artifact.

## Authority boundary

This remains an audit-only integration.

- no live LiminalDB network write;
- no Anthropic authentication;
- no prompts or model calls;
- no API calls;
- no external ticket creation;
- no deployment or merge authority;
- no durable CML memory acceptance without explicit human review.
