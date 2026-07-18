# Revolut Public Lotus Audit v0.1

## Decision

This audit converts bounded public Revolut evidence into the shared LiminalQA → Pythia → CML → LS → LiminalDB path.

```text
public web / official documentation / open-source SDK
→ exact evidence inventory
→ Lotus Decision Packet
→ artifact-only LiminalDB AuditEvents
```

The packet contains nine reviewed claims:

- 7 `CONFIRMED`
- 1 `NEEDS_EVIDENCE`
- 1 `BLOCKED`

No security vulnerability, authenticated-account defect, order-execution defect, or bounty claim is made.

## Exact public scope

- no authentication;
- no Revolut or Revolut X account access;
- no API keys or private keys;
- no direct application API calls;
- no order placement, cancellation, transfer, withdrawal, or payment;
- no fuzzing, crawling, load testing, bypass, or exploitation;
- public pages, official documentation, and the public open-source SDK only.

## Source pins

Official Revolut X tooling repository:

```text
repository: revolut-engineering/revolut-x-api
commit: 13778de69e0411ee11198dc913a3b9b0f72ac880
```

Pinned source blobs:

```text
api/src/http/request.ts                    6afcdcac728ff2fc9f347ce5e2a90a0cf8cf4495
api/src/http/errors.ts                     1f835770c03b6965d4b34e49f69689f9c1363e05
api/README.md                              b7941c9665caef638d9d5e860293b454df310d8e
api/tests/client/error-handling.test.ts    3d4c2c87d3373d1bd56c6d1567ffd8e34715cddc
revolut-x-api-for-llm.md                   db0a43aa4ce82ec496f29aa16ecfc20145dd0672
```

Public evidence inventory:

- `audits/lotus/revolut/revolut-public-evidence-v0.1.json`
- `audits/lotus/revolut/revolut-findings-v0.1.json`

## Confirmed findings

| ID | Finding | Lotus | Severity | LS risk |
|---|---|---|---|---|
| `RVLT-WEB-CURRENCY-CONTEXT-001` | Polish BTC page mixes PLN market state with EUR converter/table state | `CONFIRMED` | P2 | MEDIUM |
| `RVLT-WEB-SOL-WALLET-COPY-001` | SOL withdrawal copy offers a Solana wallet transfer and then says Bitcoin/Ethereum only | `CONFIRMED` | P2 | MEDIUM |
| `RVLT-X-RETRY-AFTER-001` | SDK exposes numeric HTTP `Retry-After` unchanged while documenting milliseconds | `CONFIRMED` | P2 | HIGH |
| `RVLT-X-PUBLIC-AUTH-DOC-001` | Public endpoints are described with three incompatible authentication contracts | `CONFIRMED` | P2 | MEDIUM |
| `RVLT-X-NODE-SIGNING-EXAMPLE-001` | Node.js signing example uses an obsolete path, symbol format, and order body | `CONFIRMED` | P2 | MEDIUM |
| `RVLT-X-MISSING-API-KEY-CURL-001` | Authenticated curl samples omit the required API-key header | `CONFIRMED` | P2 | MEDIUM |
| `RVLT-X-BTC-ORDERBOOK-ETH-SAMPLE-001` | BTC-USD order-book request is paired with an ETH response sample | `CONFIRMED` | P3 | LOW |

### Highest-priority finding: Retry-After

The SDK currently performs the equivalent of:

```text
retryAfter = Number(response.headers["Retry-After"])
```

and passes the value directly to `RateLimitError`.

Its README tells consumers that `retryAfter` is measured in milliseconds. The HTTP contract defines a numeric `Retry-After` as delay-seconds and also permits an HTTP-date.

Causal path:

```text
server: Retry-After: 2
→ SDK: retryAfter = 2
→ README consumer interprets 2 ms
→ request is repeated approximately 1000× too early
→ another 429 / avoidable retry pressure
```

Required correction:

1. parse numeric values as seconds and convert to milliseconds;
2. support HTTP-date;
3. return `undefined` for invalid values;
4. replace the existing `5000 → 5000` test with protocol-correct vectors.

## Needs evidence

### `RVLT-WEB-DEEPLINK-INTERMITTENT-001`

Earlier bounded captures showed an amount or amount-to deep link with an empty conversion result while other page data loaded. Equivalent later captures rendered successfully.

Lotus result:

```text
Pythia: ESCALATE
CML: CONFLICT
LS: UNKNOWN
Severity: UNASSIGNED
```

Evidence required before confirmation:

- 20 isolated cold browser navigations;
- separate `amount` and `amount-to` route sets;
- fresh browser context per run;
- cache state recorded;
- console messages recorded;
- HAR or equivalent request timeline;
- converter DOM state sampled until stable;
- rate-response completion correlated with converter rendering;
- no direct application API calls.

A failure should be confirmed only when the page retains the requested amount, receives or fails the required rate request, and still presents an empty or contradictory converter state in a repeatable condition.

## Blocked claim

### `RVLT-X-ASKS-DESCENDING-HYPOTHESIS-001`

The hypothesis that descending asks are automatically a sorting bug is rejected.

The current official contract explicitly states descending order for both asks and bids. That contract may be unusual, but unusual is not evidence of a defect.

Lotus preserves this as negative causal memory:

```text
claim: accidental descending-asks defect
verdict: BLOCK
memory: NEGATIVE_CAUSAL_MEMORY
```

A future claim would require runtime evidence showing that the ordering breaks the declared best-price semantics or contradicts the actual API response contract.

## What is needed for the next phase

### Public browser evidence

Safe to automate:

- locale/currency matrix across several public crypto pages;
- cold-load deep-link initialization experiment;
- console and HAR capture;
- DOM assertions for heading, converter, current rate, statistics, and conversion table;
- one bounded navigation per target and low concurrency.

### Own-account evidence

Requires the repository owner to run locally against their own account. Credentials must never be committed or shared.

Safe candidate flow:

1. open Revolut X with the owner's account;
2. record symbol, best bid/ask, timestamp, and visible connection state;
3. background the application and restore it;
4. temporarily disconnect and restore networking;
5. open order preview only;
6. compare symbol, side, quantity, fee, estimated total, and freshness state;
7. cancel before confirmation.

No real order is required for this phase.

### Runtime public API evidence

A separate bounded probe may verify whether the `/public/*` endpoints work without credentials and whether their real response matches the documented schema.

Constraints:

- only documented public endpoints;
- no authentication headers;
- maximum one request per endpoint in the evidence run;
- no scanning or parameter fuzzing;
- record response status, schema shape, timestamps, and symbol consistency;
- respect the published public rate limit.

## Submission route

The current findings are primarily product, SDK, and documentation defects. They should not be presented as security vulnerabilities without demonstrated confidentiality, integrity, authorization, or cross-account impact.

Recommended order:

1. SDK issue for `Retry-After` parsing;
2. one consolidated developer-documentation issue;
3. product feedback for currency and SOL copy defects;
4. Intigriti only if a later authorized test demonstrates a genuine security boundary failure.

## Authority boundary

The resulting packet and LiminalDB memory are advisory artifacts only.

```text
ownership = false
approval = false
execution = false
delivery = false
deployment = false
merge = false
durable_memory = false
write_mode = artifact_only
```
