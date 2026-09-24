# TradingView evidence index — 2026-07-20

## Durable reports

| Purpose | Repository path |
|---|---|
| Human-readable audit | `docs/audits/TRADINGVIEW_PUBLIC_AUDIT_2026-07-20.md` |
| Canonical machine result | `audits/browser/tradingview/public-audit-result-2026-07-20.json` |
| Public matrix configuration | `audits/browser/tradingview/public-surface-matrix.json` |
| Chart keyboard configuration | `audits/browser/tradingview/chart-keyboard-contract.json` |
| Public matrix observer | `scripts/tradingview_public_surface_probe.mjs` |
| Keyboard contract observer | `scripts/tradingview_chart_keyboard_probe.mjs` |

## Exact run map

| Evidence family | Run | Source revision | Execution revision | Artifact | Artifact digest | Result SHA-256 |
|---|---:|---|---|---:|---|---|
| Six routes × desktop/mobile matrix | `29764249089` | `8c0ab0a1b37423b0e467903335512a74ed26cd5f` | `35c4c906efc3cb9d970ec054616c4f035578c223` | `8470164725` | `sha256:2acdc7322329ea39da6cea71079b36d7048ec6761ab8d02b69656e783b4dab95` | `12221152da5b70ff1527d51b51e7520c760a0f8e5f17d15ee3a2bc04c3d811b2` |
| Focused chart keyboard contract | `29764685551` | `669e42be9533310287c0d15475bd6ec8e8f04bdc` | `74d90104c50ce363a9a3ff0befbc3ebca38f879c` | `8470305230` | `sha256:6d54f020d56cedd4c99c23b11dac340099682841c7c74e1587017cb9e8be8d4f` | `0bab1d9435569f4bb95847536fbe0e9481e0683271bd9870d50bcb1ba62d0359` |

## Public matrix screenshots

| Screenshot | SHA-256 |
|---|---|
| `desktop-home.png` | `b77572c68dc475e2c0d6bb5bcbafc9e06600efdc374a6499a85d1d0302e0724a` |
| `mobile-home.png` | `8402851711ad338324c90de0df4f06993315e3e9270bf5229b4accb1f0f8dc6f` |
| `desktop-btc-symbol.png` | `fd60ca69c949273670f49f88cd31881eb67bfd73f7113a0dd067a11cc0655063` |
| `mobile-btc-symbol.png` | `2f5ac69593e245787e7da35ad09ddf307ac7845e99e23d63fa2cbea0fa04f494` |
| `desktop-btc-chart.png` | `5ea97944bdb3a8c2bc118aa41d0ce39d7ab48d6c218205077a232c589be4837c` |
| `mobile-btc-chart.png` | `8a306561407056e9887165fad0e0838e9f2bc0c64fa5e7b1fb9c3c87551e8d5e` |
| `desktop-btc-ideas.png` | `2a2e5e8406c881693af919bdd553e5cfcac18244c5bab688be0075297a502327` |
| `mobile-btc-ideas.png` | `d0bbc64c0862aaf928f73fa641b5d394784a971de3ef1608766bc5c0709ef36e` |
| `desktop-scripts.png` | `dbe6335ac934a8e0e116ee545131e59355ec8c63e394d7e8cfe84f59fc2a3cdb` |
| `mobile-scripts.png` | `02c03ff02d55252c7b3f38b5ad506d0719c07797f00c582fc9230a3563a201d0` |
| `desktop-accessibility.png` | `ca3cc927ff2978ec3163dc0ba20de0644437f8f52de179df493f2932ec312c78` |
| `mobile-accessibility.png` | `7a2da1616b16a0f67513c2015c6ffa0ea85727e15bde56570df4834f7dedcc68` |

## Keyboard evidence screenshots

| Screenshot | SHA-256 |
|---|---|
| Desktop after initial 40 Tab presses | `0bc3dc5f3c142709fed3038da7f5f478f64c13f5905a2766df393171e60e30f1` |
| Desktop after neutral click and 40 more Tab presses | `7d73c648be7ea3416f6e9e82d06e5c071509f363350e9760444ca0e94949a034` |
| Mobile after initial 40 Tab presses | `da2a2d054d68864f176ba9916fb98b49ea10f1fcecd1bb603df9b8d082f7f03d` |
| Mobile after neutral click and 40 more Tab presses | `ec6f59a1109517173e3ee71212b0ef7b45af189113b22e9c94e7826d2331d989` |

Keyboard summary SHA-256:

```text
d23b21e14e624f9db010bfc9e9557a8d57b2d1000c493d2c2d03a2981a62a1d4
```

## Claim boundaries

### Allowed

- the public chart loaded in both profiles;
- the DOM contained sequential-focusable controls;
- 40 Tab presses before and after neutral chart activation produced zero focus targets in both profiles;
- concrete enabled controls lacked accessible names;
- the homepage contained a button nested inside another button;
- the FedCM invalid-enum console signature appeared on 12/12 observations.

### Blocked or rejected

- no claim that account sign-in is unavailable;
- no claim that market prices are incorrect;
- no `Market closed / No trades` contradiction because the browser did not reproduce it;
- no product failure inferred from aborted third-party analytics requests;
- no broad claim that every TradingView chart or browser is affected;
- no security-vulnerability claim.

## Artifact retention

Both current artifacts use 30-day retention. The exact run IDs, source/execution revisions, artifact IDs, artifact digests, result hashes, screenshot hashes, verdicts, and limitations are committed to Git so the audit remains interpretable after Actions expiry.

## Authority

Evidence only. No ownership, approval, execution, external submission, delivery, deployment, or merge authority is granted.
