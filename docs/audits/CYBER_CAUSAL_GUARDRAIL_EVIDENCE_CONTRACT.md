# Cyber Causal Guardrail Evidence Contract

The replay evidence is admissible only when all of these identities match:

```text
pull-request head SHA
= checked-out initial SHA
= replay source_sha
= checked-out final SHA
= manifest expected/initial/final SHA
```

The evidence artifact must contain exactly:

- `result.json` — the first deterministic replay;
- `result-replay.json` — a byte-identical second replay;
- `manifest.json` — source identity, authority boundary, result digest, and per-file SHA-256 records.

The manifest writer refuses:

- non-40-character or uppercase source identities;
- different expected, initial, and final SHAs;
- non-identical replay output;
- a result bound to another source SHA;
- any verdict other than the local mechanism-and-guardrail verdict;
- network, credential, external-mutation, or external-product claims.

A valid manifest proves only the integrity of the local deterministic experiment. It does not prove Tradernet internals, authenticated behavior, server resource cleanup, order impact, or production readiness.
