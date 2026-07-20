# Revolut evidence index — 2026-07-20

## Durable reports

| Purpose | Repository path |
|---|---|
| Human-readable current recheck | `docs/audits/REVOLUT_PUBLIC_RECHECK_2026-07-20.md` |
| Canonical current result | `audits/browser/revolut/public-recheck-result-2026-07-20.json` |
| Original Lotus audit | `docs/audits/REVOLUT_PUBLIC_LOTUS_AUDIT.md` |
| Original public runtime report | `docs/audits/REVOLUT_PUBLIC_RUNTIME_PROBE.md` |
| Original Docker validation | `docs/audits/REVOLUT_DOCKER_FULL_VALIDATION.md` |

## Current exact evidence

| Layer | Run | Source revision | Artifact | Artifact digest | Content digest |
|---|---:|---|---:|---|---|
| Desktop/mobile public web and docs | `29764421114` | execution `2d8aa414bfeb5289e0b245fdc1e80e86accb5c65`; branch source introduced at `d8af41591bcbfb830d5e0cd232b2204c4b9b8318` | `8470187683` | `sha256:2764aa4ee7b0b7ecacfff7a3970ac3d9c1974918505678f962d797ad8b04e051` | result `77369f80ee993535409098b9aa2278b3d5cb89bdf8db5b6c5ea2fda0aa0dc915` |
| Two public endpoint observations | `29666130304` | `c39b73a694997386ff461d40a2ccb17a63fbb0d9` | `8470029099` | `sha256:5bfb96692cd96702a63ea153cd566f329b7ad82d3e221c7cb968eb09f6386850` | result `ad5f91372f8ec71868ada76cf9cca8b1b7ecb8e6e2f44e204bbf6c577d1562d6` |
| Full current SDK/Docker validation | `29676434220` | LiminalQA `f8e86da2e98f9391ee899685991d744e293a8037`; upstream `13778de69e0411ee11198dc913a3b9b0f72ac880` | `8470077319` | `sha256:19c80a74925cc77372dde7f4434183edb6bb79cc11c8dfad74626b606046f065` | summary `cc80343c30cc7abd5906508d81304f851e85b570bc8827122959d810a2890ac7` |

## Content artifact files

The current browser artifact contains:

- `desktop-btc-pln.png` — `548478e699efdacc5ba2b7c2c2298f772a016f083f033c6d9d71b75ca87a4951`;
- `mobile-btc-pln.png` — `4c25956ee32e39de6d77db188271271d4949e3a9bff0ee615bcee477e8204fd7`;
- `desktop-sol-usd.png` — `87fe9dbc439efb9815400acf1acb36a67ede72e354758050c2878123f3cab043`;
- `mobile-sol-usd.png` — `396fb0be16a7487832d43999bcf761dc53d3c6f9acf47dd1d4b0afd4531d1be7`;
- `desktop-x-api-docs.png` — `e8099dee1c6c08029a175eecd025777296dd87c76fa0b8c7c2b6757053f0cd0c`;
- `mobile-x-api-docs.png` — `dd8c7f8ef1300dbfa018ae010f47f56bccc8cbb8253d0f43e24b5402f8f8faf2`;
- public content JSON — `77369f80ee993535409098b9aa2278b3d5cb89bdf8db5b6c5ea2fda0aa0dc915`;
- public content summary — `8fb81f3f0fd0ba435d56136f18a91c74350b6e06cd8ab2b7eeee52a4dfdf4503`;
- upstream-head record — `bfb834368c83d83d0195856bc5177567a2dca7088f236cd5bf1103595b78177c`.

## Docker evidence files

Key current SHA-256 values:

- deterministic Retry-After result — `3a42638c8caf81313d1ae7c9e60e1b38784f583d9c19b7be970bfb41200bc4f3`;
- Docker public endpoint result — `05ce185398be15f326406e99e8c5f44adfeeedceb7f650893c37b81af5632b1e`;
- Docker validation summary — `cc80343c30cc7abd5906508d81304f851e85b570bc8827122959d810a2890ac7`;
- production advisory classification — `2ec6d1a8ed0ecc84e383f396c76f9e5b72660318dd320f1da85cec9e92b55427`;
- Lotus decision packet — `f264c924def548a603fca96c090b55f8c75e5ac0ce57e5b7af4f7c4c0f7016be`.

## Evidence interpretation

A successful workflow is not itself proof. The conclusions come from the result values, screenshots, source SHA, local deterministic responses, and recorded hashes.

The public endpoint results are positive contract verification, not an access-control defect. The dependency advisory packet is a review signal, not proof of runtime exploitability.

## Retention

The current browser artifact has a 30-day Actions retention window. The current runtime and Docker artifacts have the retention configured by their original workflows. Run IDs, artifact IDs, digests, content hashes, verdicts, and limitations are committed here so the audit remains interpretable after artifact expiry.

## Authority

Evidence only. No ownership, approval, execution, external submission, delivery, deployment, or merge authority is granted.
