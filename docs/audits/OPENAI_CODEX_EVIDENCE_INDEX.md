# OpenAI Codex evidence index — 2026-07-20

## Exact identity

```text
workflow run: 29769492765
attempt: 1
child PR: #93
source head: 6b82f5c6a8b1a38d4c19986d14c16d15dcd29189
aggregate result provenance caller SHA: 6f37e3229079f522c4bd8d5877702a4d2bea803f
config SHA-256: 7d8cbdda973250af40c0ed785b708f524e473d830dc3833ec14872596f6926f2
```

## Aggregate

| Artifact | ID | Digest |
|---|---:|---|
| `liminalqa-company-audit-29769492765-1` | `8472386423` | `sha256:e0e9d750ea9c1a2abbfdc1313d19c420a3775475306a809eb19d4c7acd6b2805` |
| validated contract | `8472144881` | `sha256:73fb280ad12e4f97f3ca31474237103ee6eb47a98a77ace7b7fea560ecb62fa0` |

```text
result: a503e1582d76db97db0990183c27b2ef5ca665808d395871346bc3e363b4efff
summary: 899c289b65fb7e4e24351d608c8f6e150cb7c7ed845e6a5edea4dc2f13471782
generated evidence index: 8ca96bf14cfc2bb3b2bfc411f760f07a78e005e4cf6b001ac3d36053b3a5b7d5
```

## Cell artifacts

| Cell | Artifact ID | Artifact digest |
|---|---:|---|
| product desktop | `8472201085` | `sha256:c21081fd3fadba708790ee77b9b629bc660ef396693fdaf464f2c8841929ed4c` |
| product mobile | `8472205220` | `sha256:665cbc6b645d105a1c0c135a61c3fc5c33e1199cef295122888943d2ec6c3c6d` |
| get-started desktop | `8472251723` | `sha256:4a7542f0595c81cfbfb7d355faef0e173511ba8e9a327ecae5e8fa0db9279b9e` |
| get-started mobile | `8472257279` | `sha256:700e3375e7bfface9370239bb1c961847a613ac90861d61bb78ae5cd4e422e48` |
| docs home desktop | `8472304970` | `sha256:d02b1874cbb0251215f18e1f1e11c837708884b75331069e9f29a0e0d9ff0339` |
| docs home mobile | `8472308892` | `sha256:1755a8111773ecddf2b379c732164e599b0c662e7ff9f5f8e8019c71db7cceb1` |
| CLI docs desktop | `8472353972` | `sha256:6a2715c444cc07541ba5974594d8747a54c18e7d8a3756f52e67cd3f4a4470d9` |
| CLI docs mobile | `8472354105` | `sha256:a557ed9bb18f387dd78de6c7e0136467666e1733cf0c943e1380b0b8144de581` |
| security docs desktop | `8472378439` | `sha256:6f12e1db01ae10a10346888dbf94c8a82a1b403a51b57af1b1cd55f714d164fd` |
| security docs mobile | `8472382609` | `sha256:6e84245c0328c802dbfb5b7ed4ada29609a87080806b9a314f854ac64d0be608` |

## Interpretation boundary

The desktop product fallback is preserved but not promoted without a UA/CDN counterfactual. One Lighthouse run per cell is directional. Full screenshots, browser JSON, Lighthouse reports, exact-attempt manifests, and hashes remain in the 30-day Actions artifacts.
