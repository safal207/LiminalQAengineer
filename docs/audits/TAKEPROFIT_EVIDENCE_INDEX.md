# TakeProfit evidence index

This index maps every canonical conclusion in the 2026-07-20 public recheck to an exact workflow run, source revision, artifact, digest, and committed report.

## Canonical reports in Git

| Area | Canonical path |
|---|---|
| Human-readable recheck | `docs/audits/TAKEPROFIT_PUBLIC_RECHECK_2026-07-20.md` |
| Public identity result | `audits/browser/takeprofit/public-identity-result-2026-07-20.json` |
| Chart, quote and outage result | `audits/browser/takeprofit/public-chart-recheck-2026-07-20.json` |
| Six-surface Lighthouse result | `audits/lighthouse/takeprofit/public-recheck-2026-07-20.json` |
| Original Lighthouse/causality report | `docs/audits/TAKEPROFIT_LIGHTHOUSE_CAUSALITY.md` |
| Original chart/quote report | `docs/audits/TAKEPROFIT_CHART_QUOTE_CAUSALITY.md` |
| Quote status visibility | `docs/audits/TAKEPROFIT_QUOTE_STATUS_VISIBILITY.md` |
| Quote application order | `docs/audits/TAKEPROFIT_QUOTE_APPLICATION_ORDER.md` |
| Lotus decision packet | `docs/audits/TAKEPROFIT_LOTUS_DECISION_PACKET.md` |

## Exact evidence map

| Evidence family | Workflow run | Exact source head | Artifact ID | Artifact digest | Canonical content digest |
|---|---:|---|---:|---|---|
| Public identity sentinel | `29761310912` | `c041755c4a5c20d86e4d1bcbf3321f6e58d820f2` | `8468951631` | `sha256:f8c5b4a36109f71d6f46a098796a9c9343bdb34762702c1b4fd345a238adcbea` | raw result `187ab9c3081a84a01e940b995caa0ff76de339734aec1d0c1e4d4710f6bd9e7d` |
| Chart and quote probe | `29664421729` | `afc71b6c3cd51b4d1a17b90ac60c9c07d693df5d` | `8468880790` | `sha256:2e0d0b3255ba12a84c9f7a7bdb4146218960ba011017b066e7d785f889846c26` | result `991dd1a6e1eb6ea0d3116a530d3c2b6a82155e192f06c3fef4a2019da551167b` |
| Stale-quote counterfactual | `29664421726` | `afc71b6c3cd51b4d1a17b90ac60c9c07d693df5d` | `8468899721` | `sha256:30bf70c95a81eb4aae07c2a01ed9d09174f3e186a7e14ed52caae5d204884597` | evidence `833d572ff1976b05fc5ad60aa0cd2cb3bd11435932a566d841e8d79c73e2080d` |
| Quote visible dependency | `29666441927` | `a247b5d354b9291c25ebd35325fa66eddb08e154` | `8468928455` | `sha256:8f61a5266b1791548d23630d3405ccd0bbf9e7e2e57226a124631e58b0372c96` | evidence `1ea989b97a6b446fa20ae60a47f9999903a0ce3e293f7eab9c556c44ba49f972` |
| Quote freshness outage | `29665413400` | `fe17c3ddad4e4540d91cb30ba40456f2114dc997` | `8469010821` | `sha256:26c2444f72978c155069ba46634f748241f5584cb57b779c4f53c52c70ee5c02` | evidence `9173842b10b44337879659e7df679e6330d5efdfb73323c5888bb718380e8809` |
| Quote application order | `29666441936` | `a247b5d354b9291c25ebd35325fa66eddb08e154` | `8468987480` | `sha256:3e431a3c1c2804985894826dd8b190bf882a74371ce554ad4909e8678c6cbb95` | evidence `6f443aa848cb3794b1458c6009e7a8cc1157b7d1c062e644bc02938ad237196e` |
| Exact-attempt six-surface portfolio | `29761586937` | workflow file commit `ce39768452a804fdff7abaada81c24b27aa4b338`; PR merge SHA recorded as `2dff5a6762aefaf0fd60b8d467a751558c6972d8` | `8469097575` | `sha256:81a19491adabd886e71e892762fc63de0712aa6ae0d55470e648eb843c3ab560` | portfolio JSON `7bcd501068f95161f6f11e61f4ab723d3400ddd387468e46babd3af3160ac7e8` |

## Exact-attempt Lighthouse domain artifacts

| Target | Artifact ID | Digest | Decision-packet evidence SHA-256 |
|---|---:|---|---|
| Homepage | `8469019422` | `sha256:0d94e286b387e79b0aa5ee734fa279ed629376a5c72ec89fa66ba90fc6e42863` | `f38c951907976530a38327cb262a0ba26825f33c0a913d5c75a812c1ec9b6aed` |
| Platform | `8469023738` | `sha256:324bc7934c562ad64f71c2a21afe27c54d3472a8e6066ad14cf4b30cc05202b6` | `9711817f788b6c4acd6a91d9ba795910030f69c769870be7749233cff99fb00b` |
| Indicators | `8469043943` | `sha256:943b7b2b067e033230a02674d72e4717c319ef4ac44b473ebf63a1d6d0ecfb16` | `8b0db091c99efe15d01e2a25d45e16e3bfbb95de18a4f3a799bccc383063c567` |
| Indicator detail | `8469049333` | `sha256:e76ceff238efcd3a363be6a1fba161c770d41f22497908528da033e86feab849` | `228ddfb73d2b4e1f17ccc2616b4514f9377ba0e16bb5a7ca6634479870a92488` |
| Feed | `8469067763` | `sha256:48aca80a033282a24a41b7f0c6fb426b80bb248178544f64b0664c7e043cfd20` | `d38f6c8348b53299ab5cc9de7eef64e58b1ee3b95639f9a3c9592699634238a8` |
| Documentation | `8469091795` | `sha256:110a3ec6367f56fbd4e4eee01b15c15cc59d294256a4889b826b9abb1babb3b4` | `5abb8fadd4a44c31e9aec5c8e777f3371fd03465f3c80bc2d5c139d1b47dfdd8` |

## Artifact contents

The browser evidence artifacts preserve combinations of:

- raw or sanitized JSON results;
- Markdown summaries;
- desktop/mobile screenshots;
- baseline/treatment chart crops;
- exact-attempt manifests;
- SHA-256 manifests.

The committed canonical JSON intentionally omits raw quote bodies and other unnecessary payload details. Raw bodies remain only in the bounded temporary experiment artifact where the original workflow contract placed them.

## Rejected evidence source

The aggregate produced by re-running selected jobs inside old workflow run `29664421730` is **not** used for current comparison. Its aggregate could combine packets from different attempts because the old artifact names did not include `github.run_attempt`.

Status:

```text
REJECTED_FOR_CURRENT_COMPARISON
```

The replacement workflow `TakeProfit Exact-Attempt Public Recheck` uses run-ID-and-attempt-scoped artifact names, downloads only the active attempt, and fails unless six matching manifests are present.

## Retention and durability

- Current Actions artifacts use 14-day or 30-day retention according to their original workflow contracts.
- The human report, canonical JSON results, hashes, run IDs, source SHAs, artifact IDs, and artifact digests are committed to Git and remain available after artifact expiry.
- A workflow success state alone is never treated as proof; all findings are derived from the recorded result content.

## Authority boundary

These files provide evidence and bounded recommendations only. They grant no ownership, approval, execution, external submission, delivery, deployment, or merge authority.
