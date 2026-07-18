# Lotus Evidence Vertical Slice

Status: experimental contract-only integration.

This directory connects LiminalQA to four external protocol roles without
silently granting any repository execution or approval authority:

1. **T-Trace** records acknowledged state transitions.
2. **DRP** records the judgment and later supersession.
3. **ProofPath** provides the evidence-manifest boundary and hash verification.
4. **LiminalDB** receives the append-only storage projection.

The vertical slice is deliberately evidence-first:

```text
LiminalQA signal
  -> T-Trace transition sequence
  -> Lotus judgment (Pythia + CML + LS)
  -> DRP decision record
  -> ProofPath-style evidence manifest
  -> LiminalDB storage projection
```

## Pinned protocol inputs

| Role | Repository | Pinned commit |
| --- | --- | --- |
| transition trace | `safal207/T-Trace` | `6a0755dbe8a89decd325298ec4563b9bb16adc62` |
| decision record | `safal207/DRP` | `92e63d7d4eeb55f8eb61956da002dc8951bab1c6` |
| evidence boundary | `safal207/ProofPath` | `b94452f6ad4c5fa5d9efe80334d358d623b97e07` |
| durable event store | `safal207/LiminalDB` | `75ef9f7f403a34c60aa2ceba4cb3c97870d73e77` |

These pins establish the exact reference state used to design this adapter.
They are not vendored dependencies and do not imply conformance certification.

## Safety boundary

- A model verdict is a proposal, not external execution authority.
- `ESCALATE` means evidence is insufficient for a confirmed defect.
- An evidence manifest proves file integrity, not that the underlying claim is true.
- A LiminalDB projection is append-only input, not permission to mutate a target.
- A later decision must supersede the earlier DRP record; it must not rewrite it.
- No payment, reservation, account mutation, or destructive action is performed by
  this example.

## Example

`examples/airbnb-run-001.json` is a **planned, non-executed** Airbnb currency
atomicity investigation. It demonstrates the full contract while explicitly
remaining at evidence grade `F0` and Pythia verdict `ESCALATE`.

Run validation:

```bash
python3 scripts/validate_lotus_evidence.py
python3 -m unittest tests/test_lotus_evidence.py -v
```

The validator checks:

- pinned source SHAs are full 40-character Git hashes;
- fact, observation, and hypothesis are distinct claim kinds;
- an unexecuted run cannot claim a confirmed defect;
- T-Trace order is `sense -> transition -> commit`;
- the DRP record is immutable and references the run;
- the evidence manifest hashes match repository files;
- the LiminalDB projection preserves `valid_time` separately from
  `transaction_time`.
