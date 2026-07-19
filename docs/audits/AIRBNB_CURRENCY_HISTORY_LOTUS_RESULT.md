# Airbnb currency and browser-history Lotus result

**Decision:** no confirmed defect from the current evidence  
**Source execution PR:** #77  
**Exact execution head:** `404da0d714de334e18080138623370fdc32717f5`  
**Workflow run:** `29678020284`  
**Packet SHA-256:** `e89f580c251c707735a55689c56fa8d787b14cbe51124e2ac0ccd701cd495989`

## Matrix

The read-only Docker workflow tested three public listings. Every listing used two fresh Chromium contexts and the sequence:

```text
TRY URL → EUR URL → browser Back → browser Forward
```

No login, form submission, host contact, payment, or reservation occurred.

| Target | Attempts | Result | Lotus decision |
|---|---:|---|---|
| Antalya center | 2 | visible reservation currency followed `TRY → EUR → TRY → EUR` in both contexts | `NO_DEFECT_OBSERVED` |
| Alanya center | 2 | selected dates/page did not provide a valid reservation-price context | `NEEDS_EVIDENCE` |
| Alanya beach | 2 | selected dates/page did not provide a valid reservation-price context | `NEEDS_EVIDENCE` |

No attempt produced a reproducible inconsistent signature.

## Judgment

### Pythia

- `ALLOW_BOUNDED_NEGATIVE_RESULT` for the exact Antalya listing and date window.
- `ESCALATE` both Alanya targets because an unavailable or missing reservation-price block cannot be counted as pass or failure.
- `BLOCK` the broad claim that Airbnb generally preserves the wrong currency across browser history.

### CML

The Antalya run becomes negative causal memory for this exact listing, date window, locale, and unauthenticated profile. It does not prove universal correctness. The two Alanya targets remain conflicts awaiting available dates.

### LS

No user-control loss was observed in the valid Antalya run. User impact for the two unavailable targets is unknown because the intended reservation-price state was not present.

## Evidence

### Antalya center

- artifact: `ABNB-MATRIX-antalya-center`
- artifact SHA-256: `55030ae08db9d7f462aec48a75ce11873deb32d4f44255ffc01c3b7b1e06ad49`
- `probe-result.json`: `517a50bd54dabc417c122a0d978e283df37007455c0e550dbd0823ef72164d0e`
- manifest: `696533d042f2ef730cdd321a59dbcff6bab07c4430f312138540c17579382efa`

### Alanya center

- artifact: `ABNB-MATRIX-alanya-center`
- artifact SHA-256: `2623bb56629c88594be4dd77a450b5a828bb49c20cb0afc451a70cfdadbabd3c`
- `probe-result.json`: `e877618d03085afdade0ad0b13bdeb2e0a3e5ab715caa6dfc8223b8d3ae1f290`

### Alanya beach

- artifact: `ABNB-MATRIX-alanya-beach`
- artifact SHA-256: `a4ff4ef98ed2db605bdfcd99297ab807b4509fc4de70106bd9ac71a94359844d`
- `probe-result.json`: `f495447b405e4c7e8dad7791882dc04ee4d47053234781242194d2859e52854c`

## Next bounded experiment

Choose available date windows for the two Alanya listings, verify that the target reservation-price block is visible before starting the currency sequence, and repeat two fresh contexts. Do not promote an unavailable listing to either PASS or defect.

## Authority boundary

PR #77 remains execution-only and draft. This result PR contains adjudication and regression checks only. It does not submit an Airbnb report or grant ownership, approval, execution, delivery, external-submission, or merge authority.
