# Fixed-Scope QA Engagement Template

Copy this file for each paid sprint. Execution starts only when the required fields are confirmed.

## 1. Engagement identity

- Client:
- Product / system:
- Client owner / contact:
- Sprint name:
- Date:
- Delivery deadline:
- Fixed price:
- Retest included: yes / no

## 2. Authorization

- System owner / authorized party:
- Written authorization reference:
- Authorized environment:
- Authorized test identities / credentials:
- Authorization expiry, if any:

### Explicitly prohibited

- production access not listed above;
- real customer data unless specifically approved and necessary;
- targets not listed in scope;
- destructive testing;
- persistence or malware;
- third-party infrastructure testing;
- public-network smart-contract attack execution.

If authorization is ambiguous, stop and clarify before execution.

## 3. Critical flow

One-sentence business flow:

> Example: A test wallet may spend within per-transaction, daily, and monthly limits, and simultaneous or retried requests must not cause duplicate execution or inconsistent accounting.

### In-scope steps

1.
2.
3.
4.

### In-scope endpoints / interfaces

| Interface | Purpose | Allowed methods / actions |
|---|---|---|
|  |  |  |

### Out of scope

- 
- 
- 

## 4. Expected business rules

| Rule ID | Rule | Source / owner |
|---|---|---|
| BR-001 |  |  |
| BR-002 |  |  |

Any ambiguous rule must be marked `NEEDS_CONFIRMATION` rather than guessed.

## 5. Limits and boundaries

- Per-action limit:
- Daily limit:
- Monthly / rolling limit:
- Timeout expectations:
- Retry policy:
- Idempotency mechanism:
- Status transition rules:
- Approved concurrency level:
- Approved request rate / load ceiling:

## 6. Test data

- Synthetic identities:
- Test accounts / wallets:
- Seed state:
- Required fixtures:
- Sensitive fields that must not be collected:

## 7. Evidence policy

Allowed evidence:

- request/response excerpts;
- sanitized logs;
- screenshots;
- state snapshots;
- test run timestamps;
- build/version identifiers.

Do not store secrets in evidence bundles.

## 8. Planned test lenses

Check only those that are in scope.

- [ ] happy path
- [ ] threshold boundaries
- [ ] duplicate request
- [ ] retry after timeout
- [ ] partial failure
- [ ] controlled concurrency
- [ ] rejected-request state consistency
- [ ] asynchronous state convergence
- [ ] audit trail consistency
- [ ] recovery / safe-stop behavior
- [ ] product UX / analytics path

## 9. Deliverables

- [ ] scope snapshot
- [ ] test matrix
- [ ] run summary
- [ ] reproducible findings
- [ ] evidence bundle / evidence references
- [ ] business-priority list
- [ ] retest note

## 10. Exit conditions

Possible outcomes:

- `PASS`
- `FAIL`
- `BLOCKED`
- `INCONCLUSIVE`

The sprint is complete when:

- agreed scenarios have an explicit outcome;
- every finding has reproduction evidence;
- blocked or inconclusive areas are named;
- the client receives the final summary;
- included retest terms are recorded.

## 11. Approval to start

Client confirms:

- the target is authorized;
- the environment is correct;
- the scope is complete enough to execute;
- out-of-scope areas must not be tested;
- the stated load / concurrency ceiling is acceptable.

Client approval:

- Name:
- Date:
- Approval channel / reference:
