# Claude public web benchmark v0.1

## Purpose

This benchmark applies the existing LiminalQA Lighthouse decision-packet contract to seven official public Claude surfaces. It produces exact-run performance, accessibility, browser-best-practice, and SEO evidence without interacting with Claude models or authenticated user state.

## Exact inventory

1. `https://claude.ai/`
2. `https://claude.com/product/overview`
3. `https://claude.com/product/claude-code`
4. `https://platform.claude.com/docs/en/home`
5. `https://platform.claude.com/docs/en/api/overview`
6. `https://support.claude.com/en/`
7. `https://status.claude.com/`

The inventory uses current canonical destinations verified on 2026-07-19. Legacy Anthropic routes that redirect to Claude domains are not benchmarked as separate products.

## Exact evidence run

- workflow run: `29665084768`
- exact evidence head: `df79bc0f6330b6430fcb3c29962c293697158037`
- workflow conclusion: `success`
- seven domain jobs: `success`
- exact-run inventory validation: `success`
- portfolio artifact: `claude-public-web-portfolio-29665084768`
- portfolio artifact SHA-256: `bc084810a9a1a5ef48cfe4d3eb6186dcc176e728761f376165cd2b07eda8a117`

## Evidence-aware result

The generic portfolio produced `WARN` for all seven targets. One packet, however, is not a valid product-performance measurement: the Claude Code product page returned Lighthouse `NO_LCP` for both Largest Contentful Paint and Total Blocking Time. Its apparent Performance score of `0` is therefore classified as `NEEDS_EVIDENCE`, not as a confirmed product defect.

Across the six complete measurements:

- average Performance: `39.0`;
- LCP range: `9.92–41.43 s`;
- six of six complete measurements remain below the configured Performance threshold;
- unused JavaScript appears in six of seven target packets;
- boot-time and back/forward-cache findings each appear in five target packets.

| Surface | Perf | A11y | Best practices | SEO | LCP | TBT | Evidence state |
|---|---:|---:|---:|---:|---:|---:|---|
| Claude public shell → `/login` | 25 | 97 | 57 | 92 | 33.92 s | 3.99 s | Confirmed bounded signal |
| Claude product overview | 29 | 73 | 100 | 92 | 41.43 s | 1.52 s | Confirmed bounded signal |
| API overview docs | 33 | 86 | 100 | 100 | 12.57 s | 4.93 s | Confirmed bounded signal |
| Platform docs home | 38 | 87 | 100 | 100 | 15.49 s | 6.82 s | Confirmed bounded signal |
| Claude Status | 47 | 83 | 79 | 100 | 9.92 s | 0.40 s | Confirmed bounded signal |
| Claude Help Center | 62 | 95 | 96 | 100 | 9.94 s | 0.40 s | Confirmed bounded signal |
| Claude Code product | 0 reported | 92 | 93 | 92 | unavailable | unavailable | `NEEDS_EVIDENCE` (`NO_LCP`) |

## Main bounded findings

### 1. Claude public shell

The unauthenticated request redirected to `https://claude.ai/login` and produced Performance `25`, LCP `33.92 s`, and TBT `3.99 s`. Lighthouse estimated about `2,936 KiB` of unused-JavaScript savings and `14.48 s` of associated timing opportunity. The redirect itself was estimated at about `0.79 s`, so this run does not support calling the redirect the dominant cause.

### 2. Claude product overview

The product overview produced Performance `29`, LCP `41.43 s`, Accessibility `73`, and TBT `1.52 s`. The strongest opportunities were about `847 KiB` of unused JavaScript and about `2.43 s` of render-blocking-resource savings. Accessibility findings require separate surface-level review rather than being collapsed into the performance cause.

### 3. Claude Platform documentation

The docs landing and API overview both show material main-thread pressure:

- docs home: LCP `15.49 s`, TBT `6.82 s`, about `2,596 KiB` estimated unused JavaScript;
- API overview: LCP `12.57 s`, TBT `4.93 s`, about `2,595 KiB` estimated unused JavaScript.

This supports a recurring documentation-runtime contributor but does not prove that every Claude surface shares the same implementation or root cause.

### 4. Status and Help

The Status surface produced Accessibility `83` and Best Practices `79`, including contrast and semantic signals. The Help Center was the closest surface to the configured Performance threshold at `62`, but still produced LCP `9.94 s` in this bounded profile.

### 5. Claude Code product page

Lighthouse recorded FCP `2.22 s` and Speed Index `3.50 s`, but emitted `NO_LCP`. No claim about a real Performance score or LCP regression is publishable from this packet. The next bounded action is an exact repeat focused on LCP-candidate emission and page lifecycle behavior.

## Evidence boundary

- one passive Lighthouse navigation per exact target;
- no authentication or private workspace access;
- no prompts, conversations, API calls, model calls, tools, connectors, or agents;
- no account, subscription, billing, or file operations;
- no crawling, fuzzing, load testing, bypass attempts, exploitation, or vulnerability claims;
- at most two targets execute concurrently;
- every portfolio result must contain exactly one decision packet for every reviewed URL.

## Interpretation contract

A threshold warning is a bounded quality signal, not proof of one shared root cause. Marketing pages, the unauthenticated Claude shell, documentation, support, and status surfaces may use different runtimes and must remain causally separate until evidence supports a connection.

Redirects, transient status incidents, blocked resources, consent states, bot-protection behavior, and missing Lighthouse metrics are recorded as delivered evidence rather than silently normalized away.

Machine-readable evidence-aware interpretation is stored in `audits/lighthouse/claude/portfolio-result.json`.
