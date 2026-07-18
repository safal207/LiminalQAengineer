# Lotus Evidence Vertical Slice

Status: experimental evidence-first integration.

This directory connects LiminalQA to four external protocol roles without silently granting any repository execution or approval authority:

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

These pins establish the exact reference state used to design this adapter. They are not vendored dependencies and do not imply conformance certification.

## Safety boundary

- A model verdict is a proposal, not external execution authority.
- `ESCALATE` means evidence is insufficient for a confirmed defect.
- An evidence manifest proves file integrity, not that the underlying claim is true.
- A LiminalDB projection is append-only input, not permission to mutate a target.
- A later decision must supersede the earlier DRP record; it must not rewrite it.
- No payment, reservation, account mutation, or destructive action is performed by repository or CI examples.

## Stage 1 — evidence contract

`examples/airbnb-run-001.json` is a **planned, non-executed** Airbnb currency atomicity investigation. It demonstrates the full contract while explicitly remaining at evidence grade `F0` and Pythia verdict `ESCALATE`.

```bash
python3 scripts/validate_lotus_evidence.py
python3 -m unittest tests/test_lotus_evidence.py -v
```

The validator checks exact source pins, fact/observation/hypothesis separation, T-Trace ordering, DRP identity, manifest integrity, and separate LiminalDB valid and transaction times.

## Stage 2 — browser capture gate

`capture/airbnb-currency-atomicity-v0.1.json` defines the safe capture profile for `ABNB-RUN-002`. The matching template is `examples/airbnb-run-002.capture.json`.

The gate validates a packet created by an authorized operator or runner. It requires two independent attempts, timezone-aware timestamps, exact environment metadata, screenshots, state snapshots, a network archive, T-Trace, artifact hashes, explicit redaction, and unchanged `payment_submitted=false` / `reservation_created=false` boundaries.

```bash
python3 scripts/lotus_capture_gate.py \
  --spec integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json \
  --capture integrations/lotus/examples/airbnb-run-002.capture.json
```

The highest automatic result is `READY_FOR_REVIEW / F3`; the gate always returns `confirmed_defect=false`.

## Stage 3 — operator-guided Playwright runner

`scripts/lotus_playwright_capture.py` opens one allowlisted public Airbnb listing in headed Chromium and records three operator-confirmed checkpoints. It performs no automated clicks or form submissions. Raw HAR data is redacted and deleted before packaging.

CI validates only the no-browser plan, allowlist, redaction, context isolation, packaging, and direct `runner -> capture gate` contract. It does not install Playwright, launch a browser, or contact Airbnb.

See [`capture/PLAYWRIGHT_RUNNER.md`](capture/PLAYWRIGHT_RUNNER.md) for the detailed low-level workflow.

## Stage 4 — one-command session orchestration

`scripts/lotus_airbnb_capture_session.py` sequences:

```text
no-browser plan
→ attempt-01 in a fresh headed context
→ attempt-02 in a second fresh headed context
→ explicit human screenshot review attestation
→ deterministic finalization
→ Lotus capture gate
```

Run the bounded local session:

```bash
python3 scripts/lotus_airbnb_capture_session.py run \
  --listing-url 'https://www.airbnb.com/rooms/REPLACE_WITH_PUBLIC_LISTING' \
  --output-root artifacts/ABNB-RUN-002 \
  --acknowledge-safe-scope
```

The wrapper rejects a non-empty output directory, requires an interactive terminal, invokes subprocesses with argument vectors rather than shell strings, and never confirms a defect.

Preview the exact sequence without browser import or target contact:

```bash
python3 scripts/lotus_airbnb_capture_session.py plan \
  --listing-url 'https://www.airbnb.com/rooms/REPLACE_WITH_PUBLIC_LISTING' \
  --output-root artifacts/ABNB-RUN-002
```

```bash
python3 -m unittest tests/test_lotus_airbnb_capture_session.py -v
```

A finalized package may become `READY_FOR_REVIEW / F3`; it still cannot become a confirmed defect without a separate Pythia or human judgment.
