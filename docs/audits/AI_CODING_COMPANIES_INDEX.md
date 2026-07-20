# AI coding companies public audit index — 2026-07-20

## Portfolio

| Company/product | Exact run | Cells | Verdict | Highest automated severity | Aggregate artifact | Result SHA-256 |
|---|---:|---:|---|---|---:|---|
| OpenAI Codex | `29769492765` | 10/10 | `WARN` | `MEDIUM` | `8472386423` | `a503e1582d76db97db0990183c27b2ef5ca665808d395871346bc3e363b4efff` |
| Anthropic Claude Code | `29769523371` | 10/10 | `WARN` | `HIGH` | `8472339939` | `6038103afada359adde3d4169ff640fd4cde233a5e6be7644db2b72e78e21e40` |
| Cursor | `29769555934` | 10/10 | `WARN` | `HIGH` | `8472361710` | `9ea8033eabb499ada7b8c63d42f4ded6f57fe71506ba79bbe8ea47d10b644dd9` |

The automated severity describes the aggregate quality-gate result, not a final business severity. Human-confirmed findings are documented separately.

## Main confirmed findings

### OpenAI Codex

- visible/accessible-name mismatch on the Codex pet control;
- invalid heading progression in Codex Security docs;
- recurring localized contrast and non-descriptive-link signals;
- desktop product fallback retained only as an observer/UA/CDN candidate.

### Claude Code

- tab controls reference nonexistent ARIA panel IDs in desktop and mobile;
- desktop install-command copy buttons exclude visible command text from their accessible names;
- two unnamed keyboard links on the product page;
- repeated event-logging CORS failure with user impact unproven.

### Cursor

- `aria-hidden` home-page demos contain focusable buttons and inputs in both profiles;
- Quickstart and CLI deep links redirect to generic `/docs` rather than route-specific replacements;
- unnamed focusable docs controls and label/content mismatch;
- contrast failures across all 10 cells.

## Durable files

```text
docs/audits/OPENAI_CODEX_PUBLIC_AUDIT_2026-07-20.md
docs/audits/OPENAI_CODEX_EVIDENCE_INDEX.md
audits/companies/openai-codex/result-2026-07-20.json

docs/audits/CLAUDE_CODE_PUBLIC_AUDIT_2026-07-20.md
docs/audits/CLAUDE_CODE_EVIDENCE_INDEX.md
audits/companies/anthropic-claude-code/result-2026-07-20.json

docs/audits/CURSOR_PUBLIC_AUDIT_2026-07-20.md
docs/audits/CURSOR_EVIDENCE_INDEX.md
audits/companies/cursor/result-2026-07-20.json
```

## PR map

- Portfolio and durable reports: draft PR `#92`.
- OpenAI isolated execution: draft PR `#93`.
- Claude isolated execution: draft PR `#94`.
- Cursor isolated execution: draft PR `#95`.

Child PRs exist only to provide isolated pull refs, run IDs, and artifact namespaces. They should not be merged.

## Safety boundary

Public official pages, natural navigation, keyboard Tab observation, and Lighthouse only. No authentication, accounts, installation, CLI execution, model requests, repository connections, local-file access, MCP, agents, subscriptions, payments, forms, direct application APIs, fuzzing, load testing, exploitation, or server-state changes.

## Authority

Evidence only. No external report has been sent. No ownership, approval, remediation assignment, deployment, or merge authority is granted.
