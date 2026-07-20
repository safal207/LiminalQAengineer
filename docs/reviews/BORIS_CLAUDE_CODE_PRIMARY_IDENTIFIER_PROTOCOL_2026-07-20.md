# Boris / Claude Code #21151 — Primary Identifier Contract

Status: bounded public-evidence protocol  
Target: `anthropics/claude-code#21151`  
External authority: none

## Question

Does the public evidence support a product contract requiring collapsed file-operation events to preserve the identity of the affected object?

The investigation does **not** ask whether a specific private Claude Code TUI function is defective. The public repository does not expose the complete product renderer source, and no installed Claude Code runtime is exercised by this protocol.

## Observer coordinates

```text
N  = read-only public evidence observer
O  = issue #21151 + public comments + tracker main SHA + observation time
X  = tool event and affected object
Y  = transition from hidden identity to visible primary identifier
Z  = collapsed/expanded surface, outcome, cardinality, privacy boundary
T  = issue history and regression reports
τ  = Hello -> Mirror -> Bind -> Seal -> Flow
```

## Public evidence boundary

The workflow may verify:

- issue state, assignee, labels, timestamps, and comment count;
- public comment signals and their immutable body hashes;
- the reported regression boundary between `2.1.19` and `2.1.20`;
- demand for visible file paths, patterns, blocked targets, auditability, and configuration;
- a disclosed reference renderer against a bounded acceptance matrix.

The workflow may not claim:

- access to private Claude Code TUI source;
- current installed CLI behavior;
- that the issue is fixed;
- that the reference renderer is Anthropic implementation code;
- authority to close, label, assign, approve, or merge anything upstream.

## Contract

```text
Tool event
    -> extract primary identifier
    -> normalize for workspace and privacy
    -> bind identifier to outcome
    -> seal minimum collapsed-view fields
    -> render bounded visible output
```

### Minimum collapsed fields

```text
tool name
outcome when not successful
primary identifier
cardinality when multiple
bounded expansion hint or remaining count
```

### Tool mappings

| Tool | Primary identifier |
|---|---|
| `Read` | workspace-relative file path |
| `Write` | workspace-relative file path |
| `Edit` | workspace-relative file path |
| `Glob` | glob pattern |
| `Grep` | search pattern |

### Security rule

A blocked or denied action cannot commit an opaque collapsed message.

```text
Blocked Read 1 file
```

is insufficient because the user cannot identify the denied object without expanding the event.

A compliant reference form is:

```text
Blocked Read: src/security/policy.ts
```

The exact wording is not normative. Object identity is normative.

## Bounded matrix

The reference matrix covers:

```text
5 tools
x 2 cardinalities
x 4 outcomes
x 2 target variants
= 80 core scenarios
```

Additional edge cases cover:

- duplicate basenames;
- home-directory username redaction;
- sensitive filenames without content disclosure;
- bounded rendering of long search patterns.

## Stack roles

```text
LPI
  Hello -> Mirror -> Bind -> Seal -> Flow
  establishes presence and identity before rendering

CaPU
  Gate -> Incubate -> Commit -> Execute
  prevents blocked/denied opaque output from committing

T-Trace
  records sense -> transition -> commit for each scenario

TTM DB
  stores immutable transition truth and verifies replay

SDP
  compares verbose-only, primary-identifier, config-only,
  and full-detail hypotheses

DRP
  preserves the earlier keep-open recommendation and
  records the stronger acceptance-contract decision
```

## Verdicts

```text
READY_TO_NOTIFY_PRIMARY_IDENTIFIER_CONTRACT_SUPPORTED_IMPLEMENTATION_NOT_VERIFIED
```

means:

- the public issue remains live and assigned;
- the public evidence supports a missing-primary-identifier contract;
- the disclosed reference renderer passes the bounded matrix;
- all component contracts and evidence replays pass;
- implementation and current-product status remain unverified.

```text
BLOCKED_PRIMARY_IDENTIFIER_EVIDENCE_INCOMPLETE
```

means at least one public-source, contract, component, replay, or authority check failed.

## Publication boundary

Permitted:

- a comment linking the evidence packet;
- acceptance criteria for current-product verification;
- a recommendation to keep the issue open until the actual CLI is tested.

Forbidden:

- closing the issue;
- claiming the current release is broken or fixed without runtime evidence;
- presenting the reference renderer as Claude Code source;
- assigning ownership or implementation obligations to Boris or Anthropic.
