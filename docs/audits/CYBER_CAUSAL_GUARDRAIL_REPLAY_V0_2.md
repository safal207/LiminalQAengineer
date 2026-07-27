# Cyber Causal Guardrail Replay v0.2

## Scope and authority

This replay is a local, deterministic, standard-library-only experiment. It does not connect to Tradernet, Redis, WebSocket servers, accounts, portfolios, order endpoints, or any other external system.

Allowed:

- reproduce narrowly defined state-transition mechanisms in memory;
- compare an intentionally vulnerable model with a guarded model;
- run unit tests and deterministic replay in CI;
- create exact-head JSON and SHA-256 evidence.

Prohibited:

- credentials or authentication;
- real Redis or WebSocket connections;
- order placement, cancellation, or any financial operation;
- fuzzing, enumeration, concurrency stress, or load testing;
- claims about Tradernet internal implementation or server-side resource state;
- deployment or merge.

## Why this replay exists

Static review produced several high-confidence code candidates, but a code smell and a reproduced mechanism are not the same thing. The replay therefore asks a narrower question:

```text
observed code pattern
-> explicit ownership invariant
-> intentionally vulnerable in-memory model
-> deterministic failing transition
-> guarded model changing one load-bearing variable
-> deterministic passing transition
```

A mechanism is considered locally reproduced only when the vulnerable model fails the declared invariant and the guarded model passes the same invariant under the same inputs.

## Scenario 1: Redis identity symmetry

```text
subscribe
-> Redis SADD(channel, user_id)
-> unsubscribe
-> Redis SREM(channel, ws_id)
-> user_id remains in the Set
-> stale membership candidate
```

Guard:

```text
membership_token = user_id + ws_id + generation_id
SADD exact membership_token
SREM exact membership_token
final cardinality returns to baseline
```

Expected result:

- vulnerable model: invariant fails;
- guarded model: invariant passes.

## Scenario 2: two sockets for one user

```text
connect old socket
connect new socket
subscribe both
old socket closes late
user-wide unsubscribe runs
new socket remains physically open but loses logical subscription
```

Guard:

```text
subscriptions owned by connection + generation
old cleanup removes only old ownership
new socket continues receiving
```

Expected result:

- vulnerable survivor receives: `false`;
- guarded survivor receives: `true`.

## Scenario 3: generation fencing

```text
generation 1 connects
-> generation 2 reconnects and becomes current
-> late generation 1 disconnect arrives
-> unscoped cleanup deletes current state
```

Guard:

```text
cleanup carries generation_id
cleanup mutates only the matching generation
stale cleanup cannot delete current generation
```

## Scenario 4: Redis self-echo

```text
local send
+ publish to Redis
+ publishing instance consumes its own event
= two deliveries per intended socket
```

Guard:

```text
unique event_id
+ per-socket deduplication
= one logical delivery
```

The replay uses two sockets and one event ID. The vulnerable model produces delivery count `2` per socket; the guarded model produces `1`.

## Scenario 5: financial mutation refusal

The replay never performs a mutation. It tests only the authorization gate.

Authorization requires all of the following:

- environment is exactly `test` or `sandbox`;
- origin is an exact allowlisted HTTPS origin using reserved `.example` domains;
- account mode is explicitly `sandbox`;
- mutation flag is explicitly enabled;
- confirmation binds an unpredictable nonce;
- nonce has not been used before.

The gate must reject:

- production environment;
- non-allowlisted or visually confusing origin;
- non-sandbox account;
- missing mutation flag;
- wrong confirmation;
- replayed nonce.

Passing this gate proves only the local refusal contract. It does not authorize or perform a real order.

## Scenario 6: secret redaction

Sentinel Cookie, Authorization, SID, session, and token values are supplied to the redaction layer. The serialized evidence must not contain the sentinel values.

This does not prove every historical log sink is safe. It proves the proposed local redaction contract rejects the tested leak paths.

## Scenario 7: bounded I/O and safe HTML

- the fake transport must receive an explicit finite timeout;
- timeout values above thirty seconds are rejected by the audit helper;
- hostile HTML remains escaped text in the generated report;
- no browser or script execution occurs.

## Scenario 8: evidence-class separation

The replay preserves these classes:

| Condition | Result |
| --- | --- |
| mocked and passed | `SIMULATED_PASS` |
| skipped or not executed | `NOT_RUN` |
| evidence unavailable | `UNAVAILABLE` |
| live and passed | `LIVE_PASS` |

A simulated result can support a local mechanism claim but cannot be presented as live product evidence.

## Expected verdict

```text
CONFIRMED_LOCAL_MECHANISM_REPRODUCTION_AND_GUARDRAIL_PASS
```

This verdict requires:

- four vulnerable lifecycle models fail their declared invariant;
- all eight guarded scenarios pass;
- two complete replay outputs are byte-identical;
- source identity is an exact forty-character commit SHA;
- no network, credential, or external mutation path is used;
- initial and final worktrees remain clean;
- an immutable artifact manifest records file sizes and SHA-256 values.

## Causal conclusion boundary

The replay can support:

> The reviewed code patterns are sufficient to produce the modeled lifecycle failures, and the stated ownership guardrails prevent those failures in the deterministic local model.

The replay cannot support:

- Tradernet uses the same code;
- Redis is the upstream cause of the public quote-time contradictions;
- a production zombie connection currently exists;
- authenticated sessions behave the same way;
- any order or financial state is affected;
- the guarded model is production-ready.

## Next transition after a successful replay

The smallest justified next action is to port the same tests to the owning implementation repository or an authorized staging environment:

```text
local mechanism replay passes
-> implementation-level unit test against real classes
-> authorized staging test with internal connection and Redis metrics
-> human root-cause adjudication
```

A public outside-in test cannot complete the final server-resource step.
