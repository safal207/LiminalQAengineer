# Revolut public recheck — 2026-07-20

## Executive verdict

The current public Revolut and Revolut X surfaces were rechecked against the exact findings from the previous audit.

**Result:** all seven previously confirmed product/documentation defects remain reproducible. No additional high-confidence product defect was promoted during this pass.

The current official `revolut-engineering/revolut-x-api` `master` head remains:

```text
13778de69e0411ee11198dc913a3b9b0f72ac880
```

Therefore, the deterministic SDK result is against the current upstream source rather than an obsolete revision.

## Coordinate model

```text
O = official public URL or current SDK source
  + browser/runtime profile
  + unauthenticated state
  + observation time

N = passive public browser
  or bounded deterministic local SDK observer
```

Axes:

- `X` — route or documentation section → public claim → runtime/source contract;
- `Y` — consistent → contradictory → ambiguous → reproduced;
- `Z` — desktop/mobile browser, public runtime, network-disabled Docker;
- `T` — navigation/build → settled capture → deterministic observation → result.

## Regression status

| Finding | Fresh result |
|---|---|
| BTC/PLN page mixes PLN market context with EUR converter/table | `REPRODUCED_AGAIN` |
| SOL external-wallet copy contradicts itself | `REPRODUCED_AGAIN` |
| SDK exposes Retry-After seconds as milliseconds and HTTP-date as NaN | `REPRODUCED_AGAIN` |
| Public endpoint authentication documentation conflicts with runtime/source contract | `REPRODUCED_AGAIN` |
| Node signing example uses obsolete order path and payload | `REPRODUCED_AGAIN` |
| Authenticated curl examples omit `X-Revx-API-Key` | `REPRODUCED_AGAIN` |
| BTC-USD order-book request is paired with ETH sample levels | `REPRODUCED_AGAIN` |

## 1. BTC/PLN currency-context inconsistency

Desktop and mobile independently reproduce the same state:

```text
route and heading: BTC/PLN
market statistics: PLN / zł
hero converter: EUR
section named “Price of BTC in PLN”: EUR table
```

Example captured state:

```text
Bitcoin price: BTC/PLN
EUR BTC
Our current rate 1 BTC = €57,310.26
Stats · Market cap zł ... · 24h trading volume zł ...
Price of BTC in PLN
EUR BTC
```

The user cannot reliably determine whether the conversion control and table represent the route quote currency or a separate EUR context.

**Severity candidate:** P2 content/state consistency.

## 2. Solana wallet-support contradiction

Desktop and mobile show the same sentence:

```text
Withdraw your Solana tokens ... or send them directly to another one of your crypto wallets (Bitcoin and Ethereum only).
```

The page simultaneously offers transfer of Solana to another crypto wallet and limits the parenthetical supported set to Bitcoin and Ethereum. The intended capability cannot be established from the page.

**Severity candidate:** P2 product-copy contract.

## 3. Retry-After SDK contract mismatch

The current official SDK was built and exercised in a network-disabled Docker container against deterministic local HTTP 429 responses.

### Numeric header

```text
Retry-After: 2
public property documentation: milliseconds
observed RateLimitError.retryAfter: 2
expected under documented unit: 2000
```

### HTTP-date header

```text
observed: NaN, serialized as null in evidence
expected: non-negative millisecond delay
```

**Classification:** `CONFIRMED_RETRY_AFTER_CONTRACT_MISMATCH`.

This can cause an SDK consumer to retry roughly 1000 times earlier than intended when the server uses delay-seconds. The exact application impact depends on consumer retry logic and is not assumed here.

## 4. Public authentication documentation conflict

The same developer reference states that every request must contain:

- `X-Revx-API-Key`;
- `X-Revx-Timestamp`;
- `X-Revx-Signature`.

Its public endpoint examples instead use:

```text
Authorization: Bearer <yourSecretApiKey>
```

Fresh bounded runtime observation confirms that both documented `/public/*` endpoints return HTTP 200 with no authentication material:

- `/api/1.0/public/last-trades` — 100 items and valid `data + metadata` contract;
- `/api/1.0/public/order-book/BTC-USD` — 5 ask and 5 bid levels and valid contract.

This narrows the finding to documentation/example inconsistency. It is **not** an authentication bypass.

## 5. Obsolete Node signing example

The rendered reference still contains the obsolete contract:

```text
/api/1.0/crypto-exchange/orders
BTC/USD
type
qty
```

The current official contract uses `/api/1.0/orders`, `BTC-USD`, and `order_configuration`.

**Classification:** `CONFIRMED_DOCUMENTATION_DEFECT`.

## 6. Authenticated curl examples omit the API key

The current page contains 32 authenticated curl blocks with timestamp and signature headers. All 32 omit `X-Revx-API-Key`, despite the global authentication section marking it required.

**Classification:** `CONFIRMED_DOCUMENTATION_DEFECT`.

## 7. BTC order-book example contains ETH levels

The request example is:

```text
GET /api/1.0/public/order-book/BTC-USD
```

The paired response sample identifies `ETH`, `Ethereum`, and ETH quantities in both asks and bids.

**Classification:** `CONFIRMED_DOCUMENTATION_DEFECT`.

## Public runtime: correct behavior confirmed

The two bounded public GET requests were spaced by at least 1.1 seconds and sent without keys, signatures, cookies, bodies, or account context.

```text
PUBLIC_NO_AUTH_CONFIRMED: 2
AUTH_REQUIRED_AT_RUNTIME: 0
RUNTIME_RESPONSE_MISMATCH: 0
```

No raw prices, quantities, trade IDs, or order-book values were retained.

## Dependency advisory signal

Fresh production dependency classification:

- critical: 0;
- high: 2;
- moderate: 3;
- total: 5;
- direct high packages: 0.

Status: `ADVISORY_REVIEW_REQUIRED`.

These are transitive dependency signals. Their presence does not prove that a vulnerable code path is reachable in Revolut X, and no exploitability claim is made.

## Claims not promoted

### `amount` / `amount-to` initialization

Both current crypto routes rendered successfully in desktop and mobile. The historical intermittent empty-result hypothesis remains unresolved and was not reproduced in this capture.

### Descending asks

The current official contract explicitly specifies descending asks. This is retained as a blocked hypothesis, not a defect.

### New defect count

No new high-confidence product defect beyond the existing seven was established. The value of this pass is strong current regression evidence and confirmation that the public endpoint runtime remains correct.

## Evidence preservation

Canonical result:

```text
audits/browser/revolut/public-recheck-result-2026-07-20.json
```

Evidence index:

```text
docs/audits/REVOLUT_EVIDENCE_INDEX.md
```

Artifacts preserve:

- six desktop/mobile content screenshots;
- public content JSON and Markdown summary;
- public endpoint contract results without market values;
- Docker build/test logs;
- deterministic Retry-After result;
- Lotus decision packet;
- dependency classification;
- exact run/source manifests and SHA-256 files.

## Safety and authority boundary

No authentication, account access, private keys, tokens, orders, previews, transfers, withdrawals, payments, fuzzing, load testing, rate-limit exhaustion, or exploitation was performed.

The reports provide evidence and recommendations only. They grant no ownership, approval, external submission, execution, delivery, deployment, or merge authority.
