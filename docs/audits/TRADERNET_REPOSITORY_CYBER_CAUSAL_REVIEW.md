# Tradernet-Related Repository Cyber-Causal Review

Date: 2026-07-27  
Status: `STATIC_REVIEW_COMPLETE_RUNTIME_VALIDATION_PENDING`

## Executive verdict

The review found a meaningful cluster of code-backed security and reliability candidates in historical Tradernet tooling and in the analogous distributed WebSocket/Redis implementation in `safal207/Liminal`.

The strongest mechanisms are:

1. WebSocket ownership identities are mixed across `user_id`, `ws_id`, and WebSocket objects.
2. Redis subscription membership is added and removed using different identity domains.
3. Local delivery plus Redis publication may process the publisher's event twice.
4. Closing one socket can remove user-wide subscription state while another socket remains live.
5. Historical credential-bearing tools can expose Cookie, SID, and raw error material through arguments, logs, diagnostics, and reports.
6. The historical API framework has mutating order methods without a code-level fail-closed test-environment gate.
7. Mock, skipped, unavailable, and live tests were not consistently separated in summary claims.

These are findings about the reviewed repositories. They are **not evidence that Tradernet uses the same internal implementation**.

The current public Tradernet finding remains separate: the demo quote stream repeatedly emitted increasing sequence/revision values while last-trade time moved backward by approximately fifteen minutes. The analog repository findings provide discriminating tests for possible lifecycle mechanisms; they do not identify the upstream root cause.

## Audit boundary

Allowed:

- repository and history review;
- exact-commit comparison;
- advisory skill and audit files;
- local and read-only CI contract tests.

Not performed:

- credential use or authenticated Tradernet access;
- account, portfolio, or personal-data access;
- order placement or cancellation;
- malformed protocol testing, enumeration, fuzzing, mass subscription, or load testing;
- external contact or vulnerability disclosure;
- remediation in external repositories;
- deployment or merge.

## Exact repository set

| Repository | Exact commit | Role |
| --- | --- | --- |
| `safal207/Liminal` | `426bf5c41a6215b0fef1e9ca59df00a880491c14` | Analog distributed WebSocket/Redis implementation |
| `safal207/Proto-liminal` | `ba32132618121cf8564db7367394fb59d818b675` | Historical Tradernet WebSocket tooling |
| `safal207/test_qorer_f` | `4fe50bfa9007f142704b22666a976fdd0b5af4f6` | Historical Tradernet API/UI test framework |
| `safal207/LiminalQAengineer` | `5f0c82162d6cd37c6971a935c988d5008f34dd43` | Current bounded public quote evidence |

## Causal graph

```text
public quote observation
  increasing n/rev + ltt moves backward ~15 minutes
  -> market-data temporal-integrity defect candidate
  -> does not expose producer or internal architecture

historical test tooling
  two subscription message forms
  + no protocol-version binding
  -> old and current observations may exercise different server paths

analog WebSocket/Redis code
  mixed identity domains
  + add/remove asymmetry
  + user-wide cleanup after one socket closes
  + possible Pub/Sub self-echo
  -> candidate tests for zombie, silence-after-reconnect, and duplicate delivery
  -x-> proof of Tradernet internal root cause

credential-bearing retest
  Cookie accepted via CLI
  + complete headers logged
  + SID returned by diagnostics
  + raw response bodies logged
  -> secret exposure risk
  -> authenticated retest blocked until tooling is hardened
```

## Finding summary

| ID | Severity | Confidence | Claim |
| --- | --- | --- | --- |
| `CYB-WS-001` | High | High | Base/derived lifecycle argument-domain mismatch |
| `CYB-WS-002` | High | High | Redis membership leak candidate from `user_id`/`ws_id` asymmetry |
| `CYB-WS-003` | High | Medium | Duplicate delivery candidate from local send plus Pub/Sub self-echo |
| `CYB-WS-004` | High | High | Reconnect race candidate from user-wide cleanup after one socket closes |
| `CYB-WS-005` | Medium | High | Global connection limit counts users instead of sockets |
| `CYB-TOOL-001` | High | High | Credential-bearing headers can be logged intact |
| `CYB-TOOL-002` | Medium | High | Cookie and Authorization values can enter through process arguments |
| `CYB-PROTO-003` | Medium | High | Historical protocol-contract drift |
| `CYB-API-001` | High | High | Financial mutation methods lack operation-boundary safeguards |
| `CYB-AUTH-002` | Medium | High | Raw SID exposed by general diagnostics |
| `CYB-HTTP-003` | Medium | High | Missing request timeouts and sensitive error logging |
| `CYB-REPORT-004` | Medium | High | Unescaped content in generated HTML reports |
| `CYB-EVID-005` | High | High | Mock/live/skip evidence classes collapsed into broad success claims |
| `TN-DATA-001` | High | High | Public demo temporal-integrity defect candidate |

## Load-bearing findings

### `CYB-WS-001`: lifecycle argument domains do not align

The derived Redis manager calls base subscription methods using argument positions that do not match the base definitions.

Why this matters:

```text
wrong type accepted by dynamic Python
-> state written under wrong identity
-> later cleanup cannot find its owner
-> symptom appears during disconnect or broadcast, not at subscribe call
```

Smallest discriminator: a local fake-Redis test that inspects every local map after one subscribe/unsubscribe trajectory.

### `CYB-WS-002`: Redis add/remove identity mismatch

The channel Set is populated using `user_id`, but unsubscribe removal uses `ws_id`.

```text
SADD serialized user_id
SREM serialized ws_id
-> Set member can remain
```

This supports `RESOURCE_LEAK_CANDIDATE`, not `CONFIRMED_RESOURCE_LEAK`. Confirmation requires observing Redis cardinality return to baseline or fail to do so.

### `CYB-WS-003`: local send plus possible self-echo

The broadcast implementation sends locally and publishes to Redis. The listener's same-instance suppression is conditional on `test_mode`, which is counterintuitive for production.

Smallest discriminator: publish a single event carrying a unique event ID and count deliveries per socket with `test_mode=false`.

### `CYB-WS-004`: one stale socket can remove a live socket's state

The manager stores multiple sockets for one user. Disconnect removes only the selected socket, then performs user-wide channel cleanup.

This produces a plausible reconnect race:

```text
old socket A
new socket B connected and subscribed
late close A
-> user-wide unsubscribe
-> B remains connected but becomes silent
```

A two-socket deterministic test can confirm or reject the mechanism without external traffic.

### `CYB-API-001`: test selection is not a financial safety boundary

The historical integration test containing order placement is skipped by default. The client methods themselves remain capable of sending mutating requests whenever called with an authenticated client.

Required local guard contract before any credentialed test:

```text
exact allowlisted non-production origin
+ explicit test-account identity
+ mutation feature flag
+ one-time confirmation token
+ bounded order parameters
+ cleanup contract
otherwise -> refuse locally before network
```

No real endpoint call is needed to test this guard.

### `CYB-EVID-005`: evidence classes were collapsed

The historical report uses broad success language while:

- many tests use mocks;
- integration tests can skip on missing credentials, failed login, or unavailable endpoints;
- the client itself says endpoint paths need confirmation from actual documentation;
- skipped and unavailable behavior can therefore inflate perceived confidence.

This is a security concern because unsafe financial tooling can be trusted based on the wrong evidence class.

## Current Tradernet product finding

The current public audit observed approximately fifteen-minute backward movements in `ltt` while quote sequence and revision increased. It reproduced on `AAPL.US` and `MSFT.US`, before and after reconnect, and during a repeated-subscription phase.

Supported claim:

> The public demo stream emitted temporally contradictory field updates under the captured conditions.

Unsupported claims:

- the source is definitely Redis;
- the cause is definitely reconnect;
- the authorized and unauthenticated streams are identical;
- order execution is affected;
- a server-side zombie connection exists;
- a specific upstream service or team owns the defect.

## New security skill architecture

```text
causal-deep-audit
  -> cyber-causal-audit
      -> source and skill security gate
      -> repository threat model
      -> trust boundaries and invariants
      -> secure-code and configuration review
      -> differential and variant analysis
      -> bounded discriminating tests
      -> false-positive gate
      -> exact-head evidence

cyber-causal-audit
  -> websocket-redis-lifecycle
      -> identity domains
      -> ownership and generation fencing
      -> add/remove symmetry
      -> multi-socket cleanup
      -> exactly-once delivery intent
      -> heartbeat and crash cleanup
      -> temporal data integrity
```

## External methodology sources

The skill design is inspired, not vendored, from exact commits of:

- OpenAI security threat-model skill;
- Trail of Bits audit, false-positive, variant, static-analysis, insecure-default, sharp-edge, supply-chain, and actions-audit methods;
- Sentry security-review, bug-finding, Actions-review, skill-scanner, and skill-writing methods;
- Semgrep code-security, LLM-security, and test-driven static-analysis methods;
- Anthropic's portable Agent Skills packaging and progressive-disclosure pattern.

The exact pins, paths, licenses, adoption modes, and runtime-compatibility references are recorded in `skills/cyber-causal-audit/sources.json`.

No external skill script is executed by this branch.

## Prioritized next action

`ADD_GUARDRAIL`

Build deterministic local regression tests for:

1. base/derived method argument identity;
2. Redis Set add/remove symmetry;
3. two sockets under one user;
4. reconnect generation fencing;
5. self-published Pub/Sub event count;
6. Cookie, Authorization, SID, and error-body redaction;
7. request timeout enforcement;
8. refusal of all financial mutations outside an exact test contract;
9. HTML report escaping;
10. mock/live/skipped/unavailable evidence separation.

Completion signal: the tests reproduce the historical unsafe patterns and pass only after explicit identity, generation, redaction, timeout, evidence-class, and mutation guards exist.

Stop condition: no real credentials and no external financial endpoint are used during this phase.

## Authority conclusion

`HUMAN_REVIEW_REQUIRED`

This review supports internal prioritization and local guardrail work. It does not authorize vulnerability disclosure, external reporting, credential use, production testing, remediation in unrelated repositories, deployment, delivery, or merge.
