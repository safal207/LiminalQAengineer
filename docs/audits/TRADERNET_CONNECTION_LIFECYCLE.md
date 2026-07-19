# Tradernet public connection lifecycle audit

This audit tests whether transports naturally initiated by public Tradernet pages are released and recreated safely across a bounded lifecycle.

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

The probe records only connection metadata, normalized URLs without query strings, frame byte counts, response statuses, phase counts, DOM state flags, and coarse runtime metrics. It does not retain WebSocket payloads, response bodies, headers, cookies, authentication data, prices, portfolios, or orders.

## Zombie-connection result

Evidence run `29666251111` on exact head `4d58d54db49a8ef43260c7f5c4a2ac683c8e865f` completed successfully.

Artifact SHA-256:

```text
65fc7473982cca5ea2071b7219390b70824fb3613b8f1d59e32c918f71d7ca67
```

Neither public surface naturally opened a first-party Tradernet WebSocket during the bounded run. Therefore:

- no duplicate active first-party socket was observed;
- no reconnect storm was observed;
- no socket survived reload or navigation to `about:blank`;
- the zombie-WebSocket claim is `BLOCKED_NOT_TESTABLE`, not confirmed and not disproved for authenticated trading surfaces.

Third-party Yandex telemetry WebSocket failures remain diagnostics only. They cannot create a Tradernet product finding.

## Confirmed duplicate settings request

The lifecycle run exposed two overlapping requests to:

```text
https://tradernet.ru/stocks/security-info/ajax-get-user-settings/
```

A focused experiment repeated the observation in three independent fresh browser contexts.

Evidence run `29666496587` on exact head `6d22575cf4cca307508614d1eb6c6bfd3e5ee62d` completed successfully.

Artifact SHA-256:

```text
20f5d9fd464b63a1f65a54636129ccdb7c16b0a801ea9557efc1791a39b55088
```

Every round produced:

- two GET requests beginning in the same millisecond;
- overlapping in-flight intervals;
- HTTP 200 for both requests;
- byte-identical response-body SHA-256;
- one modern `Fetch` initiator from `chart-theoretical-info.desktop...js`;
- one legacy `XHR` initiator through jQuery from `chart_grid.js` / `l.restore`.

**Verdict:** `CONFIRMED_REDUNDANT_DUPLICATE_REQUEST`  
**Severity:** `P2_PERFORMANCE_RELIABILITY`  
**Confidence:** high (`3/3` fresh contexts)

The evidence supports a bounded dual-loader cause for this endpoint:

```text
modern chart settings loader
+
legacy chart-grid restore loader
→ concurrent duplicate GET
→ successful byte-identical responses
→ redundant browser and backend work
```

It does not establish visible chart corruption, stale quotes, account impact, or trading-decision impact.

### Recommended repair

Use one shared settings-loading owner or shared promise/cache. Both chart consumers should reuse the same in-flight result. Add a regression assertion that one chart navigation produces at most one in-flight GET for the settings endpoint.

## Candidates retained as uncertainty

### Startup settings POST

In all three focused rounds, the page naturally sent one successful POST to the settings endpoint family with an observed request-body length of `33,404` bytes. Raw request bodies were not retained.

This is `NEEDS_EVIDENCE`, not a defect. Product intent, session semantics, repeated-navigation behavior and measurable user or backend cost must be established first.

### Stale-state visibility

The public lifecycle run did not provide an active-session naturally updating first-party stream. A stale/offline-indicator conclusion therefore requires a market-open experiment with timestamped visible quote evidence and proven recovery.

## Lotus interpretation

The executable packet is:

```text
audits/lotus/tradernet/tradernet-connection-lotus-v0.1.json
```

- **Pythia:** `ALLOW` duplicate settings request; `BLOCK` zombie-WebSocket claim; `ESCALATE` stale-state and settings-POST hypotheses.
- **CML:** retains the modern-loader + legacy-loader causal path for this endpoint only; durable acceptance remains false.
- **LS:** assigns `P2` because resource waste is confirmed but misleading market state or loss of user control is not.
- **LiminalDB bridge:** artifact-only observation; no live write or durable memory acceptance.

## Deterministic defect thresholds

A product finding may be supported only when one of these boundaries is crossed:

1. more than one active first-party WebSocket exists for the same normalized URL in a lifecycle snapshot;
2. a first-party socket created before reload remains open beyond the configured grace period;
3. a first-party transport remains open or exchanges frames after navigation to `about:blank`;
4. recovery creates at least five first-party sockets with median spacing below three seconds;
5. the same first-party URL returns at least three HTTP error responses during the bounded lifecycle.

## Safety boundary

Public pages and natural browser requests only. The audit performs no authentication, direct application API calls, subscriptions created by the test, market-depth access, portfolio access, form submission, order entry, financial operation, fuzzing, load testing, exploitation, or security-vulnerability claim.

Absence of live market frames outside an active session is not classified as a defect. Third-party telemetry connections are diagnostic only.
