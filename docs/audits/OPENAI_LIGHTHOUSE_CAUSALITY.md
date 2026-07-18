# OpenAI public web Lighthouse causality audit

## Exact evidence

Primary hardened evidence run:

- GitHub Actions run: `29662883190`
- exact head: `e88177a324d08fb9f258e9ef7442a7715975b9f4`
- portfolio artifact: `openai-public-web-portfolio-29662883190`
- artifact digest: `sha256:bde5babc5e4325cfd288e0115797a6198cd93fd9b880cb9ff85d4b037fc8f7fc`
- completeness invariant: exactly seven decision packets and exact requested-URL equality with the reviewed inventory

Replication run used to assess lab variance:

- GitHub Actions run: `29662677677`
- exact head: `8edf863899d900043fc03b47d634482fb28fb4b8`
- artifact digest: `sha256:3020609dfeacdecf4214d0d1d2f3607a7909622b109ed3cf486ddf639f6f9378`

The primary result checked into this branch is copied from the hardened run, not reconstructed by hand.

## Scope and boundary

The audit performs one passive Lighthouse navigation for each exact allowlisted public surface:

- OpenAI homepage;
- unauthenticated ChatGPT shell;
- Codex product page;
- OpenAI Developers landing;
- canonical API quickstart;
- OpenAI Help Center;
- OpenAI Status.

It does not authenticate, submit prompts, call models or APIs, execute tools or agents, upload files, change accounts or billing, fuzz endpoints, perform load testing, attempt bypass or exploitation, or make vulnerability claims.

## Hardened portfolio result

**Portfolio verdict:** `WARN`  
**Targets:** 7  
**PASS:** 2  
**WARN:** 5  
**Average Performance:** 57.9  
**LCP range:** 2.69–63.00 seconds

| Surface | Perf | A11y | Best practices | SEO | LCP | TBT | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| ChatGPT public shell | 68 | 96 | 96 | 92 | 2.69 s | 1.32 s | PASS |
| Developers landing | 57 | 98 | 100 | 92 | 6.20 s | 0.77 s | WARN |
| API quickstart | 66 | 100 | 96 | 100 | 5.91 s | 0.06 s | PASS |
| Help Center | 62 | 88 | 57 | 100 | 5.18 s | 0.29 s | WARN |
| OpenAI homepage | 43 | 100 | 61 | 100 | 63.00 s | 0.91 s | WARN |
| Codex | 34 | 100 | 61 | 100 | 14.70 s | 4.44 s | WARN |
| Status | 75 | 80 | 100 | 91 | 4.32 s | 0.38 s | WARN |

A `PASS` means the four configured category thresholds were met in that run. It does not mean the packet contains no actionable findings.

## Repeated signals

- unused JavaScript appears in 6/7 packets;
- JavaScript boot-time work appears in 6/7 packets;
- LCP-element and main-thread-work findings each appear in 4/7 packets;
- forced reflow appears in 4/7 packets;
- console errors, network dependency chains, DOM size, deprecated APIs, and DevTools inspector issues each appear in 3/7 packets;
- bfcache and contrast findings each appear in 2/7 packets.

These repetitions support a broad client-side execution and rendering theme. They do **not** prove one shared codebase or one root cause across the OpenAI ecosystem.

## Causal families

### 1. OpenAI marketing runtime: heavy media plus broad JavaScript bootstrap

The homepage and Codex page provide the strongest evidence for a shared runtime contributor:

- each transfers about 3.64 MB of script;
- each reports about 2.46 MB of unused JavaScript;
- the largest wasted items are the same Next.js chunk paths and are mostly unused during the measured navigation;
- both report deprecated APIs and DevTools inspector issues;
- both complete the largest visual element late despite sub-second TTFB.

This supports `SHARED_RUNTIME_CONTRIBUTOR`, not “all OpenAI pages have the same defect.”

#### Homepage outlier

The homepage transferred about **16.78 MB**:

- images: 8.52 MB;
- scripts: 3.64 MB;
- media: 3.09 MB.

Its 63.00-second LCP was a lazily loaded image. The measured phases were approximately:

- TTFB: 0.76 s;
- load delay: 24.95 s;
- load time: 25.44 s;
- render delay: 11.85 s.

Lighthouse estimated about **7.20 MB** of savings from modern image delivery for the selected 8.34 MB image and about **2.46 MB** of unused JavaScript. The evidence supports `HEAVY_LCP_ASSET_AND_LATE_DISCOVERY` as the dominant measured cause.

The replication run measured the same page at 66.64 seconds LCP with the same selected asset and the same major image/JavaScript findings. That repeat makes the causal family more credible, while the exact phase split remains lab-sensitive.

#### Codex

Codex transferred about **10.69 MB**, including 5.73 MB of media and 3.65 MB of script. Its 14.70-second LCP included:

- TTFB: 0.75 s;
- load delay: 10.25 s;
- load time: 0.44 s;
- render delay: 3.26 s.

It also recorded 16.3 seconds of main-thread work, 6.8 seconds of JavaScript execution, 4.44 seconds of Total Blocking Time, and about 2.46 MB of unused JavaScript. The replication run produced 19.45 seconds LCP with the same broad findings. The supported cause is mixed: delayed asset discovery plus heavy client execution.

### 2. Developer portal: image delivery on the landing page, rendering and DOM cost in docs

The Developers landing page transferred about **6.31 MB**, of which 5.53 MB was images. Lighthouse estimated:

- 4.76 MB savings from modern image formats;
- 4.85 MB savings from responsive sizing.

Its LCP element was text, with about 5.58 seconds of render delay. The evidence suggests that image over-delivery competes for resources while client rendering delays even a text LCP.

The API quickstart was much lighter at about **0.84 MB** and passed the configured thresholds, but still contained:

- 61 script requests;
- 6,657 DOM elements;
- 2.6 seconds of main-thread work;
- 5.28 seconds of LCP render delay;
- browser console errors in the observed session.

The evidence supports two related but distinct causes: image over-delivery on the portal landing and DOM/client-rendering complexity in documentation.

### 3. ChatGPT public shell: small payload, execution and render delay

The unauthenticated mobile shell transferred only about **0.37 MB** and passed the configured thresholds, yet recorded:

- 4.6 seconds of main-thread work;
- 1.32 seconds of Total Blocking Time;
- 2.0 seconds of JavaScript execution;
- an LCP dominated 77% by render delay.

This is counter-evidence against the simplistic model “large transfer size causes every slow surface.” Here execution and rendering are the stronger measured contributors.

The same legal/privacy text that became the LCP element also failed contrast at approximately 3.23:1 against white in the replication evidence, below the expected 4.5:1 for the measured text size. The hardened packet again includes the contrast finding.

### 4. Help and Status: separate quality and accessibility debt

Help Center scored Performance 62 and Best Practices 57. Its evidence includes 5.5 seconds of main-thread work, 3.6 seconds of JavaScript execution, console errors, deprecated APIs, DevTools issues, and `aria-hidden` containers with focusable descendants.

Status scored Performance 75 but Accessibility 80. Its packet includes:

- ARIA attributes incompatible with element roles;
- insufficient text contrast;
- an unnamed link;
- a list item without a list parent;
- missing meta description.

These are surface-specific semantics/accessibility findings and should not be collapsed into the marketing-runtime performance cause.

## Reproducibility and variance

The two complete runs demonstrate why the evidence contract records exact head, fetch time, raw-report digest, and artifact digest:

| Measure | Replication run | Hardened run |
|---|---:|---:|
| Average Performance | 53.1 | 57.9 |
| Warning targets | 7 | 5 |
| Homepage LCP | 66.64 s | 63.00 s |
| Codex LCP | 19.45 s | 14.70 s |
| ChatGPT verdict | WARN | PASS |
| API quickstart verdict | WARN | PASS |

Threshold crossings on ChatGPT and Quickstart show normal lab sensitivity. The homepage and Codex remain the persistent high-cost outliers, and the dominant finding families remain stable.

## Cross-domain interpretation

The hardened OpenAI portfolio averaged 57.9 Performance, versus 33.8 for the recorded Tradernet portfolio and 34.0 for the recorded TakeProfit portfolio. This is not a vendor ranking: inventories, page types, content, and run moments differ.

The useful product signal is structural:

- financial and AI platforms both expose recurring JavaScript boot and unused-code costs;
- the dominant user-visible bottleneck differs by surface;
- LiminalQA preserves those differences while emitting one comparable evidence contract.

That supports the cross-domain product thesis: LiminalQA is an evidence layer for complex digital systems, not a trading-only scanner.

## Recommended fix order from the evidence

1. Run a controlled browser-local counterfactual for the homepage LCP asset: preserve page behavior but substitute an optimized version of the exact selected image.
2. Measure whether removing lazy discovery from only that LCP candidate reduces the 24.95-second load-delay phase.
3. Route-split or defer the shared marketing JavaScript payload and verify homepage and Codex independently.
4. Serve appropriately sized modern images on the Developers landing page.
5. Reduce documentation DOM size and hydration/render work, especially on the API quickstart.
6. Fix Status and ChatGPT contrast/semantic accessibility findings as separate workstreams.
7. Investigate Help Center console and DevTools issues without treating third-party support-runtime findings as proof of core OpenAI service defects.

## Non-claims

This audit does not test model correctness, prompt safety, API correctness, streaming reliability, billing, authentication, workspace permissions, data privacy, incident accuracy, or security vulnerabilities. Green workflow execution means the evidence pipeline completed; it does not mean every target passed its quality thresholds.
