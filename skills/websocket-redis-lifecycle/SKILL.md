---
name: websocket-redis-lifecycle
description: Audit WebSocket, Redis, Pub/Sub, reconnect, heartbeat, subscription, session-generation, duplicate-delivery, and zombie-cleanup lifecycles using explicit ownership invariants and bounded causal tests. Use for distributed real-time systems and quote, notification, chat, or event-stream delivery.
license: Apache-2.0
---

# WebSocket Redis Lifecycle Audit

## Purpose

Find lifecycle defects that ordinary endpoint tests miss: stale subscriptions, wrong-owner cleanup, reconnect races, self-echo duplication, orphaned Redis membership, generation confusion, hidden stale data, and resource-accounting errors.

Invoke `cyber-causal-audit` first for authority, threat modeling, exact-head evidence, external-skill gating, and false-positive adjudication.

## When to use

Use for systems containing:

- WebSocket or SSE connections;
- Redis Pub/Sub, Streams, Sets, keys, or distributed presence;
- reconnect and resubscribe behavior;
- heartbeat, ping/pong, idle timeout, or stale detection;
- per-user, per-session, per-socket, per-instance, or per-channel maps;
- initial snapshots plus incremental updates;
- more than one server instance or browser tab;
- duplicate, missing, reordered, delayed, or apparently stale events.

## When not to use

Do not run production load, mass subscription, connection floods, malformed-frame fuzzing, account mutation, order entry, or credential attacks without explicit authorization. Public outside-in tests cannot confirm server-side Redis cleanup or resource release.

## Fail-closed states

Use these states explicitly:

- `NOT_RUN` — the required transition was not executed;
- `NEEDS_EVIDENCE` — code or outside-in evidence cannot distinguish the remaining explanations;
- `BLOCKED_BY_BOUNDARY` — authority, credentials, environment, or observability are unavailable;
- `LIFECYCLE_SIGNAL` — an ownership or transition smell exists but impact is not reproduced;
- `DEFECT_CANDIDATE` — an invariant conflict is supported by code or a bounded test;
- `CONFIRMED_DEFECT` — the transition and user or system impact are reproduced inside authorized scope;
- `RESOURCE_LEAK_CANDIDATE` — cleanup is asymmetric or unobservable;
- `CONFIRMED_RESOURCE_LEAK` — authorized internal state fails to return to baseline.

A candidate is not confirmation. Missing server metrics remain `NEEDS_EVIDENCE`, not success.

## Identity domains

Before reviewing code, enumerate every identity domain:

- `user_id`;
- account or tenant ID;
- `session_id`;
- `connection_id` or `ws_id`;
- process or `instance_id`;
- `generation_id` or reconnect epoch;
- channel or topic;
- subscription ID;
- instrument or entity key;
- message sequence, revision, event ID, snapshot ID, producer ID, and source timestamp.

For every collection, key, field, argument, and Pub/Sub payload, label the identity domain it contains. A Set populated with `user_id` and cleaned with `ws_id` violates ownership symmetry.

## Core invariants

### 1. Ownership

```text
one physical connection
-> one immutable connection_id
-> one current generation_id
-> zero or more logical subscriptions owned by that connection/generation
```

A subscription may intentionally be user-scoped, but that choice must be explicit. Closing one socket must not remove another live socket's state.

### 2. Signature and call-site consistency

Base and derived methods must agree on argument order and identity meaning. Verify definitions and every call site for:

- `connect` and `disconnect`;
- `subscribe` and `unsubscribe`;
- `broadcast` and personal send;
- heartbeat cleanup;
- remote Pub/Sub handlers.

Dynamic typing can let a wrong argument order corrupt state long before the symptom appears.

### 3. Add/remove symmetry

For every state mutation, record its inverse:

| Add path | Required inverse |
| --- | --- |
| `SADD channel user_id` | `SREM channel user_id` |
| `map[ws_id] = generation` | delete exact `ws_id` generation |
| add local subscriber | remove same local subscriber |
| register callback | unregister same callback |
| increment connection metric | decrement exactly once |
| start heartbeat task | cancel and await that task |

The inverse must use the same key namespace, identity domain, serialization, prefix, and generation.

### 4. Generation fencing

Reconnect creates a new generation. Every asynchronous event, timeout, cleanup task, retry, and Pub/Sub message that can mutate current state must carry or resolve that generation.

```text
old generation cleanup
-x-> new generation state
```

A stale close event is ignored or restricted to its own generation.

### 5. Multi-socket cardinality

If `active_connections[user_id]` is a set of sockets:

- total limits count physical sockets, not distinct users;
- per-IP limits increment and decrement exactly once;
- user-level cleanup runs only when the final relevant socket closes, unless subscriptions are socket-scoped;
- metrics cannot become negative after duplicate cleanup;
- one failed send cannot delete unrelated sockets or user-wide state.

### 6. Exactly-once delivery intent

For local delivery plus Redis publication, define whether the publisher receives its own Pub/Sub event.

Valid designs include:

- local send plus unconditional self-sender suppression;
- Pub/Sub-only delivery, including self;
- unique event ID with receiver deduplication.

Invalid ambiguity:

```text
local send
+ Redis publish
+ self-message processed again
= duplicate delivery
```

A `test_mode` flag must not accidentally invert production self-echo behavior.

### 7. Snapshot and incremental semantics

Record separately:

- initial snapshot;
- resubscription snapshot;
- incremental event;
- replay or catch-up event;
- delayed versus real-time producer;
- partial field update versus full entity replacement.

A newer sequence does not prove every field is newer. Validate sequence, revision, source time, receive time, producer, entitlement, snapshot flag, and the fields actually present.

### 8. Heartbeat and cleanup

Heartbeat timeout must cause one idempotent cleanup trajectory:

```text
missing pong or idle timeout
-> close attempt
-> generation-scoped disconnect
-> local subscription cleanup
-> Redis membership cleanup
-> callback and task cleanup
-> metrics update
-> observable completion
```

If socket close fails, cleanup still runs. If cleanup runs twice, the second pass is harmless.

### 9. Redis crash model

Presence and subscription records need:

- explicit deletion on graceful close;
- TTL or leases for process death;
- instance heartbeat or epoch;
- startup reconciliation;
- no unbounded production `KEYS` scan;
- namespaced keys that cannot overwrite another instance;
- a structure representing all live instances, not only the most recent writer.

A single `user:{id}` value cannot represent simultaneous connections on several instances unless the value is explicitly multi-instance.

### 10. Backpressure and resource bounds

Check:

- inbound and outbound message-size limits;
- queue bounds and drop policy;
- send timeouts and slow-consumer handling;
- reconnect backoff and jitter;
- maximum subscriptions per socket and user;
- maximum concurrent sockets and the real counting basis;
- Pub/Sub handler exception behavior;
- listener restart without duplicate listeners or callbacks.

## Static review procedure

1. Draw all local maps and Redis keys as a state graph.
2. Annotate key and value identity domains.
3. Trace connect, subscribe, publish, unsubscribe, disconnect, timeout, shutdown, and crash.
4. Compare base and derived signatures and every call site.
5. Search for duplicate storage of the same relationship.
6. Search for add/remove, increment/decrement, create/cancel, and register/unregister asymmetry.
7. Search for self-published event suppression and event IDs.
8. Search for listener restarts that do not close the prior Pub/Sub object.
9. Search for secrets or full payloads in debug logs.
10. Find sibling variants across repositories.

## Bounded discriminating tests

### A. Two sockets, one user

```text
connect A
connect B
subscribe both
close A
assert B still receives
assert Redis/local membership represents B only
```

### B. Reconnect generation race

```text
connect generation 1
subscribe
connect generation 2
subscribe
late disconnect generation 1
assert generation 2 remains current and subscribed
```

### C. Identity symmetry

Record the exact serialized Set member after subscribe and after unsubscribe. Final cardinality must return to baseline.

### D. Self-echo

Publish one event with a unique ID. Each intended socket receives it exactly once on one and multiple instances.

### E. Duplicate subscribe

Repeat the same subscription and record separately:

- incremental delivery multiplicity;
- snapshot reinitialization;
- callback and Redis membership cardinality;
- metrics changes.

### F. Heartbeat zombie cleanup

In authorized staging only:

```text
baseline metrics and Redis state
-> abrupt network loss
-> wait bounded heartbeat timeout
-> assert connection, subscription, task, and consumer counts return to baseline
```

### G. Temporal integrity

For each entity compare consecutive events by:

- sequence and revision;
- producer or source marker;
- server receive time and source event time;
- fields actually present;
- snapshot or init flag.

Flag contradictions rather than assuming one global monotonic clock.

## Output contract

Return:

1. identity-domain table;
2. state and trust-boundary graph;
3. invariant matrix;
4. static findings with exact paths;
5. runtime test results or `NOT_RUN`;
6. generation and cleanup timeline;
7. duplicate and temporal-integrity analysis;
8. Redis baseline/final comparison when authorized;
9. competing explanations and rejected false positives;
10. smallest safe next experiment.

## Rationalizations to reject

- “The user is connected somewhere, so deleting shared state is safe.”
- “Sets deduplicate, so duplicate subscribe has no side effects.”
- “Closing the socket automatically removes Redis membership.”
- “A ping send failure proves cleanup completed.”
- “Increasing revision means every partial field is fresh.”
- “One active user equals one active connection.”
- “Pub/Sub never echoes to the publisher.”
- “The reconnect test passed, so no zombie exists.”
- “The public client cannot see the leak, so the leak is disproven.”

## Assurance boundary

This skill may identify code-backed candidates and design safe tests. Confirming server-side leaks, cross-instance races, or production availability impact requires authorized internal or staging observability. It grants no exploitation, production stress, disclosure, deployment, or merge authority.