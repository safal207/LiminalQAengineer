# Tradernet public connection lifecycle audit

This audit tests whether transports naturally initiated by public Tradernet pages are released and recreated safely across a bounded lifecycle, then follows the strongest reproducible signal through a focused duplicate-request experiment and Lotus decision packet.

## Targets

- `https://tradernet.ru/charts/MICEXINDEXCF` — public chart and realtime candidate.
- `https://tradernet.ru/terminal` — unauthenticated login surface used as a negative control.

## Lifecycle

For each target, one fresh desktop browser page performs:

```text
cold public navigation
→ 20 s bootstrap
→ 15 s browser-local offline period
→ 30 s recovery
→ one reload + 20 s observation
→ navigate to about:blank + 12 s teardown observation
```

The probe records connection metadata, normalized URLs without query strings, frame byte counts, response statuses, phase counts, DOM state flags and coarse runtime metrics. It does not retain WebSocket payloads, response bodies, headers, cookies, authentication data, prices, portfolios or orders.

## Fresh zombie-connection result

Evidence run `29687311888` on exact head `89a13d3e98f811f07f56543265ca1a8399f79c65` completed successfully.

```text
artifact: tradernet-connection-lifecycle-29687311888
artifact sha256: 9641cb67da53d947cf107d6ba0cb37eec2ee3fcc7f79c8f734a0d6948f1c953d
aggregate result sha256: 7999ae13d4d5050779786ab26a720d30b974ec08e94346407159799447a11505
```

Neither public surface naturally opened a first-party Tradernet WebSocket. Therefore:

- no duplicate active first-party socket was observed;
- no reconnect storm was observed;
- no socket survived reload or navigation to `about:blank`;
- the zombie-WebSocket claim remains `BLOCKED_NOT_TESTABLE`, not confirmed and not disproved for authenticated trading surfaces.

The lifecycle aggregate contains no confirmed finding. It retains overlapping-request signals as `NEEDS_EVIDENCE`; the settings endpoint is adjudicated separately by the focused experiment below. Third-party telemetry remains diagnostic only.

## Fresh confirmed duplicate settings request

The public chart naturally starts two overlapping GET requests to:

```text
https://tradernet.ru/stocks/security-info/ajax-get-user-settings/
```

Focused run `29687311871` on exact head `89a13d3e98f811f07f56543265ca1a8399f79c65` repeated the observation in three independent fresh browser contexts.

```text
artifact: tradernet-duplicate-settings-29687311871
artifact sha256: 0b7fb1232f828e72870951ebb44c5b4b6953a84d7fe5e3b93ab9a1b38c94ecb8
result sha256: 88624d99703c653b8be6c6f3e3a4c4f129d06269a273c440aac070b30a61666a
```

Every round produced:

- exactly two GET requests beginning in the same millisecond;
- overlapping in-flight intervals;
- HTTP 200 for both requests;
- the same two-byte response-body SHA-256;
- encoded transfer between `3,463` and `3,465` bytes per request;
- one modern `Fetch` initiator from `chart-theoretical-info.desktop...js`;
- one legacy `XHR` initiator through jQuery from `chart_grid.js` / `l.restore`.

**Verdict:** `CONFIRMED_REDUNDANT_DUPLICATE_REQUEST`  
**Severity:** `P2_PERFORMANCE_RELIABILITY`  
**Confidence:** high (`3/3` fresh contexts)

```text
modern chart settings loader
+
legacy chart-grid restore loader
→ concurrent duplicate GET
→ successful byte-identical responses
→ redundant browser and backend work
```

The evidence does not establish visible chart corruption, stale quotes, account impact or trading-decision impact.

### Recommended repair

Use one shared settings-loading owner or shared promise/cache. Both chart consumers should reuse the same in-flight result. Add a regression assertion that one chart navigation produces at most one in-flight GET for the settings endpoint.

## Candidate retained as uncertainty: startup settings POST

All three fresh contexts naturally emitted one successful POST to the settings endpoint family. Observed request-body sizes ranged from `33,187` to `33,404` bytes. Each response was HTTP 200 with the same one-byte response hash. Raw request bodies were not retained.

This remains `NEEDS_EVIDENCE`, not a defect. Product intent, session semantics, payload meaning, repeated-navigation behavior and measurable user or backend cost must be established first.

## Candidate retained as uncertainty: stale-state visibility

The public lifecycle run did not provide an active-session naturally updating first-party stream. A stale/offline-indicator conclusion therefore requires a market-open experiment with timestamped visible quote evidence and proven recovery.

## Lotus interpretation

The executable packet is:

```text
audits/lotus/tradernet/tradernet-connection-lotus-v0.1.json
```

- **Pythia:** `ALLOW` duplicate settings request; `BLOCK` zombie-WebSocket claim; `ESCALATE` stale-state and settings-POST hypotheses.
- **CML:** retains the modern-loader + legacy-loader causal path for this endpoint only; durable acceptance remains false.
- **LS:** prioritizes the P2 resource waste while acknowledging that misleading market state or loss of user control is not established.
- **LiminalDB bridge:** artifact-only observation; no live write or durable memory acceptance.

## Deterministic lifecycle thresholds

A lifecycle product finding may be supported only when one of these boundaries is crossed:

1. more than one active first-party WebSocket exists for the same normalized URL in a lifecycle snapshot;
2. a first-party socket created before reload remains open beyond the configured grace period;
3. a first-party transport remains open or exchanges frames after navigation to `about:blank`;
4. recovery creates at least five first-party sockets with median spacing below three seconds;
5. the same first-party URL returns at least three HTTP error responses during the bounded lifecycle.

## Safety and authority boundary

Public pages and natural browser requests only. The audit performs no authentication, direct application API calls, test-created subscriptions, market-depth access, portfolio or personal-data access, form submission, order entry, financial operation, fuzzing, load testing, exploitation, external ticket creation or security-vulnerability claim.

Absence of live market frames outside an active session is not classified as a defect. Third-party telemetry connections are diagnostic only. Ownership, approval, execution, delivery, external submission and merge authority remain false.
