# Valta Agent Spend Reliability Sprint — Evidence Index

Status: **EMPTY / PRE-EXECUTION**

This index maps every executed case and finding to sanitized evidence. It must never contain API keys, authorization headers, real user data, real funds information, or unrelated client data.

## Evidence policy

For every retained artifact record:

- what it proves;
- source case ID;
- UTC timestamp/window;
- whether the content is raw-sanitized or fingerprint-only;
- redaction/sanitization applied;
- SHA-256 fingerprint where practical;
- relationship to a finding or reconciliation claim.

If the client does not permit raw payload retention, keep only safe metadata and cryptographic fingerprints sufficient to tie the report to the observed run.

## Environment evidence

| Ref | Case | Artifact | What it proves | Retention mode | SHA-256 | Notes |
|---|---|---|---|---|---|---|
| ENV-001 | PRE-001 | TBD | Test/staging environment identity | TBD | TBD | |
| ENV-002 | PRE-001 | TBD | Test credential class / non-production boundary | metadata only | TBD | Never retain secret value |
| ENV-003 | PRE-001 | TBD | Test wallet/account identity | TBD | TBD | Use alias/hash if required |
| ENV-004 | PRE-001 | TBD | Frozen limit values/reset boundary | TBD | TBD | |
| ENV-005 | PRE-001 | TBD | Approved concurrency ceiling | metadata only | TBD | |

## Sequential control evidence

| Ref | Case | Artifact | What it proves | Retention mode | SHA-256 | Finding |
|---|---|---|---|---|---|---|
| SEQ-001 | S-PERTX-001 | TBD | Below-limit baseline | TBD | TBD | |
| SEQ-002 | S-PERTX-002 | TBD | Exact-boundary behavior | TBD | TBD | |
| SEQ-003 | S-PERTX-003 | TBD | Above-limit rejection + state cleanliness | TBD | TBD | |
| SEQ-004 | S-DAILY-001 | TBD | Sequential daily-cap enforcement | TBD | TBD | |
| SEQ-005 | S-MONTH-001 | TBD | Sequential monthly-cap enforcement | TBD | TBD | |

## Concurrency evidence

| Ref | Case | Artifact | What it proves | Retention mode | SHA-256 | Finding |
|---|---|---|---|---|---|---|
| CON-001 | C-DAY-001 | TBD | Simultaneous requests at remaining daily boundary | TBD | TBD | |
| CON-002 | C-MONTH-001 | TBD | Simultaneous requests at remaining monthly boundary | TBD | TBD | |
| CON-003 | C-PERTX-001 | TBD | Per-request validation under simultaneous arrival | TBD | TBD | |
| CON-004 | C-BURST-001 | TBD | Client-approved bounded burst outcome | TBD | TBD | |

## Idempotency/retry evidence

| Ref | Case | Artifact | What it proves | Retention mode | SHA-256 | Finding |
|---|---|---|---|---|---|---|
| IDEM-001 | I-001 | TBD | Same idempotency identity / same payload | TBD | TBD | |
| IDEM-002 | I-002 | TBD | Repeated request after original response | TBD | TBD | |
| IDEM-003 | I-003 | TBD | Duplicate while original pending, if authorized | TBD | TBD | |
| IDEM-004 | I-004 | TBD | New request identity behavior | TBD | TBD | |
| RETRY-001 | R-001 | TBD | Client-provided timeout/retry fixture | TBD | TBD | |

## Partial-failure evidence

| Ref | Case | Artifact | What it proves | Retention mode | SHA-256 | Finding |
|---|---|---|---|---|---|---|
| PART-001 | P-001 | TBD | Status/ledger/counter/wallet consistency after authorized failure fixture | TBD | TBD | |

## Reconciliation evidence

| Ref | Case | Artifact | What it proves | Retention mode | SHA-256 | Finding |
|---|---|---|---|---|---|---|
| REC-001 | REC-001 | TBD | Accepted request set vs final accounting state | TBD | TBD | |
| REC-002 | REC-001 | TBD | Counter delta vs accepted financial effects | TBD | TBD | |
| REC-003 | REC-001 | TBD | Final statuses vs wallet/ledger state | TBD | TBD | |

## Finding evidence map

Create one row per claim, not merely one row per finding.

| Finding | Claim | Evidence refs | Reproduced? | Retest evidence | Notes |
|---|---|---|---|---|---|
| VALTA-F-001 | TBD | TBD | TBD | TBD | |

## Final integrity check

Before delivery confirm:

- [ ] every executed case has at least one evidence reference or a documented evidence limitation;
- [ ] every finding claim links to concrete evidence;
- [ ] no secret/API key/auth header is present;
- [ ] no real user data or unrelated client data is present;
- [ ] timestamps use UTC;
- [ ] evidence filenames match the run ledger;
- [ ] fingerprints are recomputed after final sanitization;
- [ ] `NOT_RUN` and `INCONCLUSIVE` cases are visible in the report;
- [ ] report conclusions do not exceed the evidence boundary.
