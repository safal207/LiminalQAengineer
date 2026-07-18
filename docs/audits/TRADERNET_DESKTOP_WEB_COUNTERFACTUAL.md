# Tradernet desktop-web hero counterfactual

## Question

Does the mobile late-discovery defect reproduce on the public desktop web page, and would an additional hero preload improve desktop LCP?

## Method

The experiment used the public Russian-language page:

```text
https://tradernet.ru/?site_lang=ru
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

The first discovery run established that desktop uses:

```text
https://tradernet.ru/images/2022/invest/hero.light.1x.webp
```

This differs from the mobile experiment, where the observed LCP resource was the `2x` variant.

The treatment inserted one browser-local response-stage preload for the exact desktop `1x` LCP resource.

## Result

**LiminalQA verdict:** `NO_ADDITIONAL_EFFECT`  
**Confidence:** `MEDIUM`  
**Evidence run:** `29662406306`  
**Exact head:** `4b7f2a1946987dcb62c8e8b4086a0728a3f38aac`

| Median metric | Desktop baseline | Extra preload | Difference |
|---|---:|---:|---:|
| Hero request begins | 683.1 ms | 772.0 ms | +88.9 ms |
| Hero response completes | 1,168.8 ms | 1,227.2 ms | +58.4 ms |
| LCP | 2,284.0 ms | 2,504.0 ms | +220.0 ms |
| FCP | 2,284.0 ms | 2,504.0 ms | +220.0 ms |
| Hero loaded → LCP gap | 1,239.2 ms | 1,296.8 ms | +57.6 ms |
| Long-task total | 90.0 ms | 96.0 ms | +6.0 ms |
| Script transfer | 1,278,079 bytes | 1,278,079 bytes | unchanged |
| Script requests | 55 | 55 | unchanged |

The desktop baseline already reports the exact LCP image with initiator type `link`. Therefore, the image is already scheduled early enough on desktop.

The additional preload did not improve request timing or LCP. The observed differences are small and unfavorable to treatment, so they should be treated as run-to-run noise rather than proof that preload harms the page.

## Causal conclusion

```text
Desktop HTML
  → existing link resource hint
  → exact 1x hero requested around 0.68 s
  → hero downloaded around 1.17 s
  → render / visibility / runtime gap around 1.24 s
  → desktop LCP around 2.28 s
```

The mobile cause does **not** reproduce on desktop:

```text
Mobile baseline
  → 2x hero discovered around 7.32 s
  → LCP around 11.36 s

Desktop baseline
  → 1x hero discovered around 0.68 s
  → LCP around 2.28 s
```

This narrows the primary report to **Mobile Web / responsive resource scheduling** rather than a universal Tradernet web defect.

## Remaining desktop issue

Desktop is materially healthier, but it is not fully optimized:

- approximately 1.24 seconds remain between hero response completion and LCP;
- 55 JavaScript requests transfer approximately 1.28 MB;
- the exact same script volume remains when adding preload.

A separate desktop investigation should focus on DOM insertion, CSS visibility, animation, rendering and shared runtime cost rather than another image preload.

## Reporting language

Recommended wording:

> The severe late-discovery defect is confirmed on Mobile Web and does not reproduce under the tested Desktop Web profile. Desktop already schedules its exact `1x` LCP image through a link resource hint and reaches median LCP around 2.28 seconds. The mobile page instead discovers its `2x` hero around 7.32 seconds and reaches LCP around 11.36 seconds.

## Evidence

```text
artifact: tradernet-desktop-hero-preload-counterfactual-29662406306
sha256: 2541c133fde90ef9722015ef85b769276016e9370d337a0a7837532f125fd142
```

Machine-readable summary:

```text
audits/lighthouse/tradernet/desktop-hero-preload-counterfactual-result.json
```
