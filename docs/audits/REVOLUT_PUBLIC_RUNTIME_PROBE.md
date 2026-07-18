# Revolut X public runtime probe v0.1

## Purpose

This probe checks the runtime behavior of the two endpoints that the official Revolut X material describes as public and unauthenticated:

```text
GET /api/1.0/public/last-trades
GET /api/1.0/public/order-book/BTC-USD
```

It answers three bounded questions:

1. Does the endpoint respond without authentication at this instant?
2. Does the response have the documented top-level shape?
3. Are timestamp and order-book ordering types consistent with the current public contract?

A successful result is a QA/API-contract observation. It is not a vulnerability claim.

## Safety boundary

The workflow performs exactly two HTTP requests:

- one GET per endpoint;
- at least 1.1 seconds between requests;
- no API key;
- no signature or timestamp auth headers;
- no cookies;
- no request body;
- no account access;
- no order, transfer, withdrawal, payment, or mutation.

This stays below the Revolut public VDP automation ceiling of two requests per second.

## Data minimisation

The generated artifact does not persist raw response bodies or market values.

For each endpoint it stores only:

- HTTP status and final URL;
- content type;
- response byte length and SHA-256;
- top-level JSON keys;
- item or price-level counts;
- first-object field names;
- timestamp JSON type;
- whether asks and bids are descending when price fields can be parsed.

The report therefore proves the observed contract shape without retaining prices, quantities, trade identifiers, or order-book contents.

## Classifications

| Classification | Meaning |
|---|---|
| `PUBLIC_NO_AUTH_CONFIRMED` | HTTP 200 and the documented structural shape were observed without auth headers. |
| `AUTH_REQUIRED_AT_RUNTIME` | Runtime returned HTTP 401 or 403 without auth. |
| `RUNTIME_RESPONSE_MISMATCH` | A response was received but status or schema did not match the public contract. |
| `NETWORK_UNAVAILABLE` | The runner could not reach the host; this is not evidence of service unavailability. |

## Commands

```bash
python3 -m unittest tests/test_revolut_public_runtime_probe.py -v
python3 scripts/revolut_public_runtime_probe.py \
  --output reports/revolut-runtime/public-endpoints.json
```

## Interpretation for Lotus

### Both endpoints confirm public no-auth behavior

The earlier documentation contradiction narrows to a documentation/example defect: the runtime and official open-source contract agree that `/public/*` is unauthenticated, while the rendered Developer Reference examples should be corrected.

### Runtime requires authentication

The contradiction becomes stronger: current runtime behavior conflicts with the official repository contract. This still requires careful reporting as an API-contract defect, not an authentication bypass.

### Network unavailable

Keep the claim at `NEEDS_EVIDENCE`. Repeat once from a normal browser or another controlled runner; do not infer outage or access control from DNS or runner restrictions.

## Explicit non-goals

This probe does not:

- enumerate endpoints;
- alter query parameters;
- fuzz symbols or payloads;
- test rate-limit exhaustion;
- test authenticated endpoints;
- access any user account;
- retain live trading data;
- prove financial or security impact.

## Next evidence after this probe

The remaining higher-value work requires the researcher's own Revolut X account and must stay preview/read-only:

```text
reconnect or resume
→ verify market-data timestamps
→ open an order preview
→ compare symbol, source currency, quantity, fee and estimated total
→ stop before confirmation
```

No private key, cookie, token, account identifier, or unredacted HAR should be committed or shared.
