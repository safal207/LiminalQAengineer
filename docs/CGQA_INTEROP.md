# ContractGraph-QA interoperability v0.1

LiminalQA can validate a ContractGraph-QA bounded-evidence artifact and derive
candidate seeds for another independent CGQA run. Both commands are local,
file-first operations: they do not open LIMINAL-DB and make no network request.

## Import evidence

```bash
cargo run --bin limctl -- import-cgqa \
  --input cgqa-evidence.json \
  --output liminal-import-receipt.json
```

The receipt says only that the strict v0.1 profile was accepted as bounded
evidence. It preserves all three producer statuses, including
`not_found_within_bound`; it does not turn that status into `pass`.

## Export candidates

```bash
cargo run --bin limctl -- export-cgqa-candidates \
  --input cgqa-evidence.json \
  --output liminal-candidates.json \
  --derived-at 2026-09-03T10:03:00Z \
  --operation-id liminal-candidate-derivation-001 \
  --attempt-id attempt-001
```

Mapping is deliberately asymmetric:

| CGQA source status | LiminalQA candidate | Meaning |
|---|---|---|
| `violated` | `replay_regression` | Replay and verify the observed failure independently |
| `inconclusive` | `verification_debt` | Review the bound and gather missing evidence |
| `not_found_within_bound` | none | Do not manufacture a passing or failing candidate |

Every candidate export contains
`classification=non_authoritative_seed`, `mayAuthorizeAction=false`, and
`requiresCgqaVerification=true`.

## Contracts and conformance

- CGQA evidence is producer-owned by ContractGraph-QA.
- The consumer pin records the exact producer commit and schema SHA-256 in
  [`schemas/interop/cgqa-liminalqa-evidence-v0.1.external-contract.json`](../schemas/interop/cgqa-liminalqa-evidence-v0.1.external-contract.json).
- LiminalQA candidate schema:
  [`schemas/interop/liminalqa-cgqa-candidates-v0.1.schema.json`](../schemas/interop/liminalqa-cgqa-candidates-v0.1.schema.json)
- LiminalQA import receipt schema:
  [`schemas/interop/liminalqa-cgqa-import-receipt-v0.1.schema.json`](../schemas/interop/liminalqa-cgqa-import-receipt-v0.1.schema.json)
- Golden CGQA fixture:
  [`liminalqa-core/tests/fixtures/cgqa-liminalqa-evidence-v0.1.json`](../liminalqa-core/tests/fixtures/cgqa-liminalqa-evidence-v0.1.json)

The Rust decoder denies unknown fields and validates exact subject identity,
time ordering, adapter digest, status counts, artifact metadata, verification
debt, and the evidence/authorization boundary.

## Boundary

LiminalQA candidates are hypotheses, not findings. They cannot authorize an
action and cannot compute an LTP continuity verdict. ContractGraph-QA remains
the independent oracle for replaying candidate paths against the exact subject.
