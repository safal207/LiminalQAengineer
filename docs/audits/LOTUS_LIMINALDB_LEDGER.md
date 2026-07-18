# Lotus → LiminalDB Ledger Bridge v0.1

## Why this repository is the next Lotus connection

The current Lotus path already answers four different questions:

```text
LiminalQA — what was observed?
Pythia    — is the claim supported?
CML       — what causal memory may be proposed?
LS        — how does the condition affect user control?
```

The remaining operational burden is persistence. Exact heads, workflow runs, artifact digests, rejected hypotheses, conflicts, and superseded evidence are still easy to copy manually into another report and lose later.

LiminalDB is the best next repository because its role is append-only event sourcing, replay, snapshots, WAL-backed persistence, and a Mirror Timeline. The bridge adds no new verdict and grants no authority. It records the existing Lotus decision path as deterministic events.

## Flow

```text
LiminalQA finding
→ evidence_observed
→ Pythia judgment
→ pythia_judged
→ CML proposal/conflict/negative memory
→ cml_memory_proposed
→ LS user-control assessment
→ ls_control_assessed
→ unified decision
→ lotus_decided
→ hash-linked JSONL ledger
→ replayed current-state snapshot
```

Each finding produces exactly five events in a fixed order. Findings are sorted by `finding_id`. Every event contains:

- source Lotus packet SHA-256;
- previous event SHA-256;
- exact event payload;
- canonical CML identifier;
- unchanged `audit_only` authority boundary;
- its own canonical SHA-256.

The final event hash is the ledger head. Replaying the JSONL must reproduce the checked snapshot byte-for-byte.

## Outputs

The bridge generates:

- `lotus-ledger.jsonl` — append-only deterministic event chain;
- `lotus-ledger-snapshot.json` — current state reconstructed from the ledger;
- `manifest.sha256` — file-level artifact hashes.

The first cross-domain packet contains seven findings, so the exact ledger contains 35 events.

## What becomes easier

1. A finding can be reconstructed without searching several PR descriptions.
2. New evidence can supersede old evidence without deleting the prior state.
3. A blocked hypothesis remains visible as negative causal memory.
4. CI can prove that the snapshot is a replay of the ledger.
5. Future OpenAI, Claude, Tradernet, TakeProfit, Airbnb, or other audits can use one persistence contract.

## Current boundary

This version writes a LiminalDB-compatible artifact only. It does not open a network connection to a live LiminalDB node and does not mutate another repository or service.

```text
mode: audit_only
ownership: false
approval: false
execution: false
delivery: false
deployment: false
merge: false
```

A later adapter may ingest the verified ledger into a local LiminalDB instance through its WebSocket or SDK surface. That requires a separately reviewed scope and must preserve the same exact packet hash and authority boundary.

## Why not ProofPath or LTP first?

ProofPath becomes valuable when Lotus begins executing external actions such as sending reports, opening vendor tickets, changing production state, or merging code. It provides a pre-execution authorization boundary.

LTP becomes valuable when multi-agent execution traces themselves need deterministic replay.

The present bottleneck is earlier and simpler: durable evidence memory and supersession. Therefore LiminalDB provides the largest reduction in manual work now.
