# Tradernet mobile hero preload counterfactual

## Question

Under the tested mobile 3G profile, is late discovery of the exact `2x` hero a material contributor to LCP, and what bottleneck remains after browser-local preload?

## Method

Target:

```text
https://tradernet.ru/?site_lang=ru
```

Exact configured and machine-validated LCP resource:

```text
https://tradernet.ru/images/2022/invest/hero.light.2x.webp
```

Two variants were alternated for three rounds on one GitHub-hosted Chrome runner:

1. **Baseline** — unmodified public navigation.
2. **Hero preload** — browser-local response-stage modification inserting:

```html
<link
  rel="preload"
  as="image"
  href="https://tradernet.ru/images/2022/invest/hero.light.2x.webp"
  fetchpriority="high"
>
```

Each run used:

- a fresh browser context;
- disabled cache;
- mobile viewport `412 × 823` at device scale factor `2.625`;
- the same mobile user agent;
- emulated 3G network: 150 ms latency, 210,000 B/s download and 95,000 B/s upload;
- CPU throttling rate `4`;
- 15 seconds of post-load observation;
- no authentication, API calls, financial operations or server-state changes.

The strict collector required:

- exactly one main-document interception in every treatment run;
- the configured hero URL to remain the timed resource in every run;
- the configured hero URL to remain the LCP resource in every run;
- no navigation, interception or observer errors.

The causal claim is intentionally bound to the exact resource URL. Element identity is recorded in raw evidence but is not required for the verdict.

## Result

**LiminalQA verdict:** `SUPPORTED`  
**Confidence:** `MEDIUM`  
**Evidence run:** `29685443275`  
**Exact evidence head:** `e593d747118415bc8ac0931824cd4fb73d707c2d`

| Median metric | Baseline | Browser-local preload | Treatment − baseline |
|---|---:|---:|---:|
| Hero request begins | 7,202.4 ms | 673.2 ms | **−6,529.2 ms** |
| Hero response completes | 11,024.4 ms | 2,810.6 ms | **−8,213.8 ms** |
| LCP | 11,044.0 ms | 7,652.0 ms | **−3,392.0 ms / 30.71% improvement** |
| Hero loaded → LCP gap | 20.4 ms | 4,824.3 ms | +4,803.9 ms |
| FCP | 7,248.0 ms | 7,652.0 ms | +404.0 ms |
| Long-task total | 1,184.0 ms | 1,167.0 ms | −17.0 ms |
| Script transfer | 1,277,150 bytes | 1,277,150 bytes | unchanged |
| Script requests | 56 | 56 | unchanged |

Every treatment run:

- modified exactly one main document;
- inserted the browser-local preload;
- requested the exact configured hero with initiator type `link`;
- retained that exact URL as the LCP resource;
- completed without navigation or interception errors.

Every baseline run retained the same exact configured hero as both the timed resource and LCP resource, with initiator type `img`.

## Causal conclusion

Late discovery is a material contributor in this bounded synthetic mobile model.

```text
Baseline
HTML response around 0.68 s
  → application/runtime work
  → exact 2x hero requested around 7.20 s
  → hero downloaded around 11.02 s
  → LCP around 11.04 s

Preload treatment
HTML response around 0.64 s
  → exact 2x hero requested around 0.67 s
  → hero downloaded around 2.81 s
  → render / visibility gate around 4.82 s
  → LCP around 7.65 s
```

The preload advances median resource discovery by approximately 6.53 seconds and improves median LCP by approximately 3.39 seconds. Script count and transfer bytes are identical, and long-task time is nearly unchanged, so the measured improvement is consistent with resource scheduling rather than reduced JavaScript delivery.

The treatment also exposes a separate bottleneck:

> The exact hero completes around 2.81 seconds but median LCP occurs around 7.65 seconds.

The remaining approximately 4.82-second gap should be investigated as a separate render or visibility problem. Possible mechanisms include DOM timing, CSS visibility, animation, reconciliation or delayed paint opportunity; the current packet does not select one of these as proven.

## Recommended fix order

1. Expose the exact responsive mobile LCP resource in initial HTML.
2. Apply `fetchpriority="high"` or an equivalent exact-resource priority mechanism.
3. Verify that only the intended responsive hero variants transfer for the viewport.
4. Instrument DOM insertion, style visibility, animation and rendering timing for the remaining post-load gap.
5. Repeat the same bounded protocol against a deployed implementation before estimating production impact.

## What this does not prove

- The synthetic treatment is not deployed production behavior.
- Three alternating runs per variant do not establish field-performance certainty.
- The result does not generalize to all devices, networks, sessions or authenticated surfaces.
- The verdict is bound to the exact hero URL, not a same-element claim.
- This is not a security finding or penetration test.

## Evidence

```text
artifact: tradernet-hero-preload-counterfactual-29685443275
artifact sha256: 083f59a21d5fecb5e541537f1e83888f0fe62adad622ec87aa8a8372132189eb
result sha256: 52a773d549c956ec22302d81f438c082e78ddc669b0a9947448730e7519ea923
summary sha256: 52e31fab2587983398882bac79f383131de8aa6e27f731320df6542bea76a174
```

Machine-readable result:

```text
audits/lighthouse/tradernet/hero-preload-counterfactual-result.json
```

## Boundary

Public-page browser-local QA experiment only. No authentication, API calls, financial operations, fuzzing, load testing, exploitation or server-state changes were performed.
