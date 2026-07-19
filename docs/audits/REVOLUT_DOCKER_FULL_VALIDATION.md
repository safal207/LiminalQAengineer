# Revolut Docker full validation v0.1

## Purpose

This validation runs the official `revolut-engineering/revolut-x-api` source at exact commit
`13778de69e0411ee11198dc913a3b9b0f72ac880` inside Docker and then replays the
LiminalQA → Pythia → CML → LS → LiminalDB evidence path in a separate Python
container.

It is designed to answer four bounded questions:

1. Does the official monorepo install, typecheck, lint, format-check, test, and build from the pinned source?
2. Does the built SDK still expose `Retry-After` in a way that contradicts its documented millisecond contract?
3. Do all repository Python tests, the Revolut Lotus packet, and the LiminalDB memory export pass in an offline container?
4. Do the two documented public endpoints still return their expected schema without authentication from a clean container?

## Docker isolation

Two base images are pulled and their observed registry digests are stored in the artifact:

- `node:22-bookworm-slim`
- `python:3.12-slim`

The official source checks run with `--network=none` after `npm ci` finishes.
The Retry-After probe also runs with `--network=none` and replaces `fetch` with a
local deterministic 429 response.

Network access is allowed only for:

- pulling the two container images;
- installing the exact lockfile dependencies;
- `npm audit --omit=dev`;
- one GET to each of the two documented public endpoints, separated by 1.1 seconds.

## Checks

### Official Revolut X monorepo

```text
npm run typecheck
npm run lint
npm run format:check
npm run sync-skills:check
npm test
npm run build
```

The root `npm test` command includes each workspace's autonomous test script,
including the integration-test package's unit configuration. Secret-dependent
agent tests (`npm run test:agent`) are deliberately excluded because they require
external model credentials and are not necessary to validate the SDK contract.

### Runtime Retry-After contract

The built SDK receives two deterministic 429 responses:

```text
Retry-After: 2
Retry-After: Sun, 19 Jul 2026 00:00:02 GMT
```

The evidence records the public `RateLimitError.retryAfter` value without making
a live Revolut request. The expected current classification is:

```text
CONFIRMED_RETRY_AFTER_CONTRACT_MISMATCH
```

This means the numeric HTTP delay is exposed as `2` while the SDK documentation
instructs consumers to treat it as milliseconds, and the HTTP-date form is not
converted into a usable delay.

### Lotus and memory replay

The Python container runs all `tests/test_*.py` tests with networking disabled,
then regenerates:

- the nine-finding Revolut Lotus Decision Packet;
- nine LiminalDB-compatible `AuditEvent` records;
- the transition report;
- exact SHA-256 manifests.

### Public runtime observation

The Python container repeats exactly two unauthenticated GET requests:

```text
GET /api/1.0/public/last-trades
GET /api/1.0/public/order-book/BTC-USD
```

No raw market data is retained. The artifact stores only status, schema shape,
counts, ordering booleans, and response hashes.

### Dependency advisory check

`npm audit --omit=dev --json` records the current production dependency advisory
state. High or critical advisories fail the final gate but do not prevent artifact
upload.

## Safety boundary

The workflow does not use or request:

- API keys, private keys, signatures, cookies, tokens, or account identifiers;
- authenticated endpoints;
- orders, order previews, cancellations, transfers, withdrawals, or payments;
- rate-limit exhaustion, fuzzing, enumeration, or load testing;
- secret-dependent agent/model tests.

A passing run proves the pinned source and bounded public contracts only. It does
not prove the absence of account-level, trading, authorization, or financial-impact
defects.

## Evidence artifact

The workflow uploads:

```text
revolut-docker-full-validation-<run_id>
```

The archive contains image digests, exact source SHAs, every command log and exit
code, Retry-After observations, public endpoint summaries, the production audit
report, Lotus packets, LiminalDB events, and `SHA256SUMS.txt`.
