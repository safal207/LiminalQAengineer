# Tradernet desktop-web hero counterfactual

## Question

Under the tested desktop profile, is late discovery of the exact desktop hero the dominant LCP cause, and does adding another preload improve the result?

## Method

Target:

```text
https://tradernet.ru/?site_lang=ru
```

Exact desktop LCP resource:

```text
https://tradernet.ru/images/2022/invest/hero.light.1x.webp
```

Three baseline and three treatment runs were alternated on the same GitHub-hosted Chrome runner.

Desktop profile:

- viewport: `1440 × 900`;
- desktop Chrome user-agent;
- disabled browser cache;
- emulated broadband: 40 ms latency, approximately 10 Mbps download and 5 Mbps upload;
- no CPU throttling;
- 10 seconds of post-load observation;
- no authentication, API calls, form submissions or server-state changes.

The treatment used browser-local response-stage modification and inserted one preload for the exact `1x` LCP resource. The strict collector required exactly one main-document interception in every treatment round and verified that the configured hero remained both the timed resource and the LCP resource.

## Result

**LiminalQA verdict:** `NO_ADDITIONAL_EFFECT`  
**Confidence:** `MEDIUM`  
**Evidence run:** `29685227556`  
**Exact head:** `c8c8708eedbe8130adfa71e25a448d4fd5484f6c`

| Median metric | Desktop baseline | Extra preload | Treatment − baseline |
|---|---:|---:|---:|
| Hero request begins | 748.6 ms | 790.2 ms | +41.6 ms |
| Hero response completes | 1,138.1 ms | 1,182.3 ms | +44.2 ms |
| LCP | 2,356.0 ms | 2,448.0 ms | +92.0 ms |
| FCP | 2,356.0 ms | 2,448.0 ms | +92.0 ms |
| Hero loaded → LCP gap | 1,244.8 ms | 1,229.7 ms | −15.1 ms |
| Long-task total | 89.0 ms | 93.0 ms | +4.0 ms |
| Script transfer | 1,278,079 bytes | 1,278,079 bytes | unchanged |
| Script requests | 55 | 55 | unchanged |

Every baseline run recorded the exact desktop hero with initiator type `link`. Every treatment run:

- intercepted exactly one main document;
- inserted the browser-local preload;
- preserved the exact configured hero as the timed resource and LCP resource;
- completed without navigation or interception errors.

## Causal conclusion

```text
Desktop HTML
  → existing link resource hint
  → exact 1x hero requested around 0.75 s
  → hero downloaded around 1.14 s
  → render / visibility / runtime gap around 1.24 s
  → desktop LCP around 2.36 s
```

The strict rerun does not support missing preload as the dominant desktop cause. Adding another preload neither advanced the resource request nor improved LCP. The small unfavorable treatment deltas are bounded laboratory observations and are not proof that preload harms production performance.

## Remaining desktop hypothesis

A separate desktop investigation should focus on the median approximately 1.245-second gap between hero response completion and LCP, including:

- DOM insertion timing;
- CSS visibility and animation;
- rendering opportunities;
- shared runtime cost.

This desktop result is independent from the mobile counterfactual, which is revalidated separately against its own exact `2x` configured resource and artifact.

## Evidence

```text
artifact: tradernet-desktop-hero-preload-counterfactual-29685227556
sha256: ba6c75465b7290d6e7be2b7f0fa0b3a85e72a8720c4e0732cf47f556d5be6b18
result sha256: 3146db898650011c2cd0788cfda75a7258023976060c17c96696eb035d5cc3bf
```

Machine-readable summary:

```text
audits/lighthouse/tradernet/desktop-hero-preload-counterfactual-result.json
```

## Boundary

This is a public-page, browser-local QA experiment. It performs no authentication, API calls, financial operations, fuzzing, load testing, exploitation or server-state change. Three alternating runs per variant provide directional evidence, not field-performance certainty.
