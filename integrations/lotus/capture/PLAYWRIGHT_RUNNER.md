# Airbnb Playwright Capture Runner

Status: operator-guided evidence collection only.

The runner opens one allowlisted public Airbnb listing in a fresh headed Chromium context. It performs no clicks, form submissions, payment actions, or reservation actions. The operator manually prepares three checkpoints while the runner records screenshots, state snapshots, a redacted HAR, and T-Trace records.

## Install locally

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

Playwright is not installed or executed by CI. CI runs only the standard-library plan, packaging, redaction, allowlist, orchestration, and regression checks.

## Recommended: one-command session

The session wrapper executes the plan, two independent attempts, screenshot-review attestation, finalization, and capture gate in one bounded interactive flow:

```bash
python3 scripts/lotus_airbnb_capture_session.py run \
  --listing-url 'https://www.airbnb.com/rooms/REPLACE_WITH_PUBLIC_LISTING' \
  --output-root artifacts/ABNB-RUN-002 \
  --locale en-US \
  --timezone Europe/Istanbul \
  --ip-country TR \
  --acknowledge-safe-scope
```

The output directory must be absent or empty. This prevents artifacts from an earlier session being mixed into the new evidence package.

After both browser attempts, the wrapper pauses and requires the exact token `REVIEWED`. Enter it only after manually examining every generated PNG for personal or unrelated information. The wrapper then finalizes the package and invokes the existing capture gate.

Preview the exact command sequence without importing Playwright or contacting Airbnb:

```bash
python3 scripts/lotus_airbnb_capture_session.py plan \
  --listing-url 'https://www.airbnb.com/rooms/REPLACE_WITH_PUBLIC_LISTING' \
  --output-root artifacts/ABNB-RUN-002
```

The wrapper passes argument vectors directly to Python subprocesses and never uses a shell command string.

## Low-level: validate the runner plan

```bash
python3 scripts/lotus_playwright_capture.py plan \
  --profile integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json \
  --capture-template integrations/lotus/examples/airbnb-run-002.capture.json
```

This command imports no browser module and performs no target interaction.

## Low-level: capture attempt 1

```bash
python3 scripts/lotus_playwright_capture.py run \
  --profile integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json \
  --capture-template integrations/lotus/examples/airbnb-run-002.capture.json \
  --listing-url 'https://www.airbnb.com/rooms/REPLACE_WITH_PUBLIC_LISTING' \
  --attempt-id attempt-01 \
  --output-root artifacts/ABNB-RUN-002 \
  --locale en-US \
  --timezone Europe/Istanbul \
  --ip-country TR \
  --acknowledge-safe-scope
```

Repeat with `attempt-02`. Each invocation creates a fresh browser context and unique context ID.

At each checkpoint the operator records the visible currency and total:

1. `before` — dates and one guest selected in the initial currency;
2. `after_currency` — currency changed manually;
3. `after_history` — Back and Forward performed manually.

The runner never automates these interactions. It aborts known mutating requests whose paths indicate payment or reservation submission, but that filter is a defense-in-depth boundary rather than authorization to approach a final commitment step.

## Redaction

After Chromium closes, the runner:

- redacts authorization, cookie, CSRF, cookie-object, and request-body fields from the HAR;
- writes `network.har`;
- deletes `network.raw.har`;
- records the redaction count and digest.

Screenshots still require human review. Do not finalize until personal data, account information, host details not needed for the report, and unrelated browser content have been removed or masked.

## Low-level: finalize two attempts

```bash
python3 scripts/lotus_playwright_capture.py finalize \
  --profile integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json \
  --capture-template integrations/lotus/examples/airbnb-run-002.capture.json \
  --output-root artifacts/ABNB-RUN-002 \
  --confirm-screenshots-reviewed
```

Finalization requires:

- at least two attempt directories;
- unique attempt IDs and unique browser context IDs;
- identical declared environments;
- intact screenshot, state, HAR, and trace hashes;
- explicit human screenshot-redaction attestation.

It creates:

```text
artifacts/ABNB-RUN-002/
├── attempts/
│   ├── attempt-01/
│   └── attempt-02/
├── bundle/
│   ├── screenshots-before.zip
│   ├── screenshots-after.zip
│   ├── network-archives.zip
│   ├── states-before.json
│   ├── states-after.json
│   └── transitions.ttrace.jsonl
├── capture.json
└── evidence-manifest.json
```

Validate the resulting package:

```bash
python3 scripts/lotus_capture_gate.py \
  --spec integrations/lotus/capture/airbnb-currency-atomicity-v0.1.json \
  --capture artifacts/ABNB-RUN-002/capture.json
```

## Truth boundary

A complete repeated capture may reach `READY_FOR_REVIEW / F3`. The runner, session wrapper, and capture gate never set `confirmed_defect=true`. Pythia or a human reviewer must compare the exact states, network evidence, expected product rule, and user impact before any defect or bounty claim is made.
