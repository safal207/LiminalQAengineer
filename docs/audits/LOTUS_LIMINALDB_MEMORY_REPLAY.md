# Lotus → LiminalDB Memory & Replay Adapter v0.1

## Purpose

The adapter turns a deterministic Lotus Decision Packet into append-friendly LiminalDB `AuditEvent` JSONL records.

```text
LiminalQA evidence
→ Pythia judgment
→ CML scoped causal memory
→ LS user-control impact
→ Lotus Decision Packet
→ LiminalDB AuditEvent JSONL
→ history and transition comparison
```

It does **not** connect to a live database, make network requests, or accept memory automatically. The first version emits an exact artifact that can be inspected, hashed, archived, replayed, and later ingested by a separately authorized LiminalDB deployment.

## Exact LiminalDB contract pin

- repository: `safal207/LiminalDB`
- commit: `75ef9f7f403a34c60aa2ceba4cb3c97870d73e77`
- contract: `sdk/ts/src/protocol-types.ts`
- blob SHA: `fd733971aaae089df770062bcf7f2c2d6d19ca1d`
- event surface: `AuditEvent`

The generated envelope uses:

```json
{
  "id": "lotus-...",
  "ts": "2026-07-19T12:00:00+03:00",
  "kind": "audit",
  "actor": "liminalqa-lotus",
  "action": "lotus.finding.observed",
  "details": {}
}
```

## Determinism

The adapter never calls the wall clock. `observed_at` and the exact source commit are explicit inputs.

The event ID is derived from:

- Lotus packet SHA-256;
- per-finding packet SHA-256;
- canonical CML identifier;
- observation timestamp;
- exact source commit.

Re-exporting the same observation produces the same event IDs and JSONL. Append mode suppresses duplicate event IDs without rewriting older records.

## Commands

Generate the Lotus packet first:

```bash
python3 scripts/lotus_qa_decision_packet.py \
  --contract standards/lotus-qa/lotus-qa-contract-v0.1.json \
  --findings audits/lotus/lotus-findings-v0.1.json \
  --output-dir reports/lotus
```

Export one LiminalDB-compatible event per finding:

```bash
python3 scripts/lotus_liminaldb_memory.py export \
  --packet reports/lotus/lotus-decision-packet.json \
  --observed-at "$(git show -s --format=%cI HEAD)" \
  --source-commit "$(git rev-parse HEAD)" \
  --output reports/lotus/liminaldb-events.jsonl
```

Append a later observation idempotently:

```bash
python3 scripts/lotus_liminaldb_memory.py export \
  --packet reports/lotus/lotus-decision-packet.json \
  --observed-at "2026-07-26T12:00:00+03:00" \
  --source-commit "$(git rev-parse HEAD)" \
  --output history/lotus-events.jsonl \
  --append
```

Read one causal history:

```bash
python3 scripts/lotus_liminaldb_memory.py history \
  --events history/lotus-events.jsonl \
  --canonical-id tradernet.hero.late_discovery \
  --output reports/lotus/history.json
```

Compare consecutive observations:

```bash
python3 scripts/lotus_liminaldb_memory.py compare \
  --events history/lotus-events.jsonl \
  --output reports/lotus/transitions.json
```

Initial transition labels include:

- `STILL_PRESENT`;
- `STILL_PRESENT_IN_CHANGED_FORM`;
- `NOW_CONFIRMED`;
- `REOPENED_CONFIRMED`;
- `EVIDENCE_REGRESSED`;
- `CLAIM_REJECTED`;
- `UNCHANGED_DECISION`.

## Safety and authority boundary

- `write_mode` is `artifact_only`;
- no live LiminalDB write occurs;
- no remote repository is fetched or attested at runtime;
- no CML proposal becomes durable merely because an event was exported;
- `ownership`, `approval`, `execution`, `delivery`, `deployment`, and `merge` remain `false`;
- a human must separately authorize any future persistent ingestion or memory acceptance.

The adapter provides durable-format evidence. It does not grant durable authority.
