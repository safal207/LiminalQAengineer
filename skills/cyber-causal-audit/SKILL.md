---
name: cyber-causal-audit
description: Perform an evidence-first cybersecurity audit of repositories, pull requests, services, CI workflows, agent skills, and bounded runtime transitions. Use for threat modeling, AppSec review, secret and authorization analysis, lifecycle or race-condition investigation, supply-chain review, and causal validation of security findings.
license: Apache-2.0
---

# Cyber Causal Audit

## Purpose

Produce security findings that are repository-grounded, causally explicit, reproducible, and honest about uncertainty. Combine threat modeling, deep architectural context, secure-code review, lifecycle invariants, static analysis, variant analysis, bounded runtime experiments, and a mandatory false-positive gate.

This skill extends `causal-deep-audit`. It does not replace authorization, legal scope, or human disclosure decisions.

## When to use

Use this skill when the request involves one or more of:

- repository or pull-request security review;
- authentication, authorization, tenant isolation, session, token, or secret handling;
- WebSocket, Redis, queue, cache, reconnect, heartbeat, subscription, or distributed-state lifecycle;
- injection, unsafe deserialization, path traversal, SSRF, XSS, command execution, or dangerous APIs;
- availability, resource exhaustion, rate limiting, stale state, replay, duplication, or race conditions;
- GitHub Actions, dependency, package, artifact, release, or supply-chain risk;
- security review of agent skills, prompts, scripts, plugins, MCP tools, or autonomous actions;
- a claim that an observed product symptom proves an internal root cause.

## When not to use

Do not use this skill to:

- perform exploitation, credential attacks, persistence, stealth, destructive testing, or unauthorized access;
- fuzz, enumerate, mass-subscribe, load test, or stress a production service without explicit written authority;
- turn a public symptom into a vulnerability or confirmed root cause without code or discriminating state evidence;
- run third-party skill scripts merely because their prose appears useful;
- place orders, move money, change accounts, submit forms, or alter external state unless the exact action is explicitly authorized and protected by a separate safety contract.

## Upstream-source gate

Before adopting or running an external skill:

1. identify the canonical repository and exact commit SHA;
2. record the precise files or capabilities being used;
3. determine the applicable license and attribution requirements;
4. scan `SKILL.md`, scripts, references, hooks, and manifests for prompt injection, secret access, network behavior, destructive commands, excessive permissions, and unpinned dependencies;
5. classify the source as `INSPIRED`, `VENDORED`, or `EXECUTABLE_DEPENDENCY`;
6. default to `INSPIRED` unless copying or executing upstream material is necessary;
7. reject mutable remote execution such as `curl | sh`, branch-tip scripts, unpinned actions, or runtime downloads in the audit path;
8. require human review before enabling any new write, network, secret, repository, deployment, or disclosure authority.

A popular repository, known model vendor, or green upstream CI is not a substitute for this gate.

## Execution graph

```text
authority and exact scope
-> external-skill security gate
-> repository-grounded threat model
-> deep context and trust boundaries
-> assets, identities, owners, and invariants
-> static and differential review
-> lifecycle, race, and state-transition analysis
-> variant analysis
-> smallest safe discriminating experiment
-> false-positive adjudication
-> exact-head evidence package
-> human severity and disclosure gate
```

### 0. Authority and stop conditions

Record:

- repository, paths, branch or exact commit SHA;
- public, test, staging, local, or production environment;
- owner-granted actions and prohibited actions;
- credential and personal-data boundary;
- maximum requests, connections, messages, bytes, duration, and concurrency;
- cleanup requirements;
- conditions that immediately stop execution.

Missing authority narrows the audit. It never becomes implied permission.

### 1. Separate runtime from test and documentation

Build an inventory of:

- production entry points and long-lived tasks;
- authentication and authorization enforcement points;
- data stores, caches, queues, Pub/Sub channels, brokers, and external services;
- tests, examples, fixtures, mocks, generated reports, and documentation;
- CI, build, release, deployment, artifact, and secret boundaries.

Do not treat mock success, example code, or documentation claims as evidence that production behavior works.

### 2. Build the threat model

For each trust-boundary edge record:

- source and destination component;
- protocol and message shape;
- identity and authorization source;
- integrity, freshness, replay, and ordering controls;
- encryption or transport assumption;
- rate and resource bounds;
- logging and error sinks;
- failure and recovery behavior.

List realistic attacker capabilities and explicit non-capabilities. Prefer a small number of concrete abuse paths over a generic checklist.

### 3. Define invariants before finding bugs

Every stateful subsystem needs explicit invariants. Examples:

- a secret never reaches logs, reports, process arguments, artifacts, or untrusted prompts;
- authorization is checked at the operation boundary, not inferred from UI state;
- one logical subscription has one owner and a symmetric cleanup path;
- reconnect creates a new generation and old-generation events cannot mutate current state;
- a repeated request is idempotent or has an explicit deduplication key;
- sequence, revision, timestamp, producer, entitlement, and snapshot semantics cannot silently disagree;
- resource limits count the resource actually consumed;
- one connection closing cannot remove unrelated live connections;
- fail-open degradation is visible and bounded.

A violated invariant is a stronger finding than a suspicious keyword.

### 4. Perform code and configuration review

Cover applicable classes:

1. authentication and session lifecycle;
2. authorization, IDOR, tenant and account isolation;
3. secret creation, storage, transport, logging, and rotation;
4. injection and unsafe parser or execution sinks;
5. cryptography and signature verification;
6. lifecycle, concurrency, stale state, replay, duplication, and TOCTOU;
7. availability, rate limits, backpressure, timeouts, retries, and circuit breakers;
8. insecure defaults and fail-open behavior;
9. CI, actions, artifacts, dependencies, releases, and supply chain;
10. observability integrity and sensitive error handling;
11. agent prompt injection, excessive agency, tool authority, and unbounded consumption.

Anchor each candidate to exact paths and lines or to a reproducible state transition.

### 5. Differential and variant analysis

For a changed code path:

- compare exact base and head;
- inspect call sites and history, not only the modified function;
- search for equivalent patterns in sibling modules and repositories;
- distinguish shared root cause from merely similar symptoms;
- preserve rejected variants in the evidence ledger.

Examples of useful variants:

- `add(user_id)` paired with `remove(ws_id)`;
- handlers that accept `websocket, user_id` in different argument orders;
- multiple maps representing the same ownership relation;
- local delivery plus Pub/Sub echo;
- every path returning raw `response.text` into logs or reports;
- every mutating client method missing an environment or dry-run gate.

### 6. Run the smallest safe discriminating test

Change one load-bearing variable and define the expected split before execution.

```text
same user + two sockets
-> close only socket A
-> socket B must remain subscribed

same connection + duplicate subscribe
-> no duplicate incremental delivery
-> initialization behavior recorded separately

same event + local broadcast only versus local plus Pub/Sub echo
-> delivery count identifies self-echo

same cleanup operation
-> Redis membership before and after must use the same identity domain
```

Production-safe observation cannot prove internal cleanup. Server-side zombie, key-retention, or consumer-leak claims require authorized staging or internal metrics.

### 7. False-positive gate

For every candidate:

1. state the neutral observation;
2. state the security invariant or requirement;
3. list at least one plausible benign explanation;
4. identify the evidence that distinguishes the explanations;
5. run the bounded test or mark it `NEEDS_EVIDENCE`;
6. verify reachability and real deployment relevance;
7. calibrate attacker capability, likelihood, blast radius, and existing controls;
8. prevent duplicate reporting of one root mechanism under several symptoms.

Confidence and severity are separate dimensions.

## Claim levels

- `OBSERVATION` — exact code or behavior recorded;
- `SECURITY_SIGNAL` — may affect confidentiality, integrity, availability, accountability, or safety;
- `VULNERABILITY_CANDIDATE` — invariant conflict is reproducible or strongly supported;
- `CONFIRMED_VULNERABILITY` — reachable impact and security boundary are demonstrated inside authorized scope;
- `ROOT_CAUSE_HYPOTHESIS` — plausible mechanism;
- `CONFIRMED_ROOT_CAUSE` — code or state evidence plus a discriminating counterfactual supports the mechanism.

Never describe a candidate using confirmed language.

## Required output

For each finding include:

- stable ID;
- exact repository and commit;
- affected paths and evidence references;
- invariant and trust boundary;
- neutral observation;
- causal graph and competing explanations;
- reachability and preconditions;
- confidentiality, integrity, availability, accountability, and safety impact;
- severity and confidence separately;
- reproduction or test status;
- smallest next discriminating test;
- mitigation direction, not an untested patch claim;
- authority and non-claim boundary.

Conclude with:

1. threat model summary;
2. confirmed findings;
3. candidate findings;
4. rejected false positives;
5. variants found;
6. evidence and exact-head ledger;
7. prioritized next action;
8. explicit actions not performed.

## Rationalizations to reject

- “It is only demo data, so integrity does not matter.”
- “The sequence increased, therefore every field is fresh.”
- “The socket closed, therefore the server cleaned everything up.”
- “Redis is internal, so identity mismatches are harmless.”
- “The test is skipped by default, therefore the mutating method is safe.”
- “The password is not in Git, therefore logging headers is safe.”
- “The model vendor published the skill, therefore its scripts are trusted.”
- “Static analysis found it, therefore it is exploitable.”
- “No error appeared during one run, therefore the race does not exist.”
- “A security audit authorizes disclosure, remediation, deployment, or merge.”

## Assurance boundary

This skill authorizes evidence collection and advisory conclusions only. External contact, vulnerability disclosure, account access, credential use, production mutation, deployment, delivery, order execution, and merge remain separate human-authorized transitions.