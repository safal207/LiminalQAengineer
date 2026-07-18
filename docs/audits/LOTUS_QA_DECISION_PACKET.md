# LiminalQA Lotus Decision Packet v0.1

**Packet:** `lotus-qa-cross-domain-2026-07-19-v0.1`  
**Findings:** 7  
**Packet SHA-256:** `7c77d1ac2ee5872936ac4c90b48a28b3d8c2fd713ab7cf53ab8606feb2d3d7ff`  
**Authority:** `audit_only`; ownership, approval, execution, delivery, deployment, and merge grants are all false.

## Flow

```text
LiminalQA signal
→ Pythia: evidence-backed ALLOW / BLOCK / ESCALATE
→ CML: scoped causal memory, recurrence, conflict, supersession
→ LS: user visibility, timeliness, reversibility, and control risk
→ unified Lotus Decision Packet
```

## Summary

- Pythia: `{'ALLOW': 5, 'BLOCK': 1, 'ESCALATE': 1}`
- Unified: `{'BLOCKED': 1, 'CONFIRMED': 5, 'NEEDS_EVIDENCE': 1}`
- User-control risk: `{'LOW': 1, 'MEDIUM': 3, 'NONE': 1, 'UNKNOWN': 2}`
- Durable accepted memories: **0** — all current memories remain proposals pending human review.

## Findings

| ID | Domain | Pythia | CML | LS risk | Status | Severity |
|---|---|---|---|---|---|---|
| `OPENAI-HOMEPAGE-LCP-OBSERVATION-001` | openai | ALLOW | PROPOSED_RECURRING | MEDIUM | CONFIRMED | P2 |
| `OPENAI-HOMEPAGE-W750-CAUSE-001` | openai | ESCALATE | CONFLICT | UNKNOWN | NEEDS_EVIDENCE | UNASSIGNED |
| `OPENAI-SHARED-JS-CONTRIBUTOR-001` | openai | ALLOW | PROPOSED_RECURRING | LOW | CONFIRMED | P2 |
| `OPENAI-STATUS-ACCESSIBILITY-001` | openai | ALLOW | PROPOSED_SINGLE | MEDIUM | CONFIRMED | P2 |
| `TAKEPROFIT-CHARTSTORE-REGRESSION-001` | takeprofit | ALLOW | PROPOSED_RECURRING | UNKNOWN | CONFIRMED | P2 |
| `TRADERNET-HERO-DISCOVERY-001` | tradernet | ALLOW | PROPOSED_SINGLE | MEDIUM | CONFIRMED | P2 |
| `TRADERNET-REDIRECT-DOMINANT-001` | tradernet | BLOCK | NEGATIVE_CAUSAL_MEMORY | NONE | BLOCKED | UNASSIGNED |

## Priority

Confirmed: `OPENAI-HOMEPAGE-LCP-OBSERVATION-001`, `OPENAI-SHARED-JS-CONTRIBUTOR-001`, `OPENAI-STATUS-ACCESSIBILITY-001`, `TAKEPROFIT-CHARTSTORE-REGRESSION-001`, `TRADERNET-HERO-DISCOVERY-001`

Escalate: `OPENAI-HOMEPAGE-W750-CAUSE-001`

Blocked claims: `TRADERNET-REDIRECT-DOMINANT-001`

## Lotus boundary

> The packet can guide review, but it cannot approve, execute, deliver, deploy, or merge anything.
