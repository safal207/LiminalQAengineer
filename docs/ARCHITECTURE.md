# LiminalQA-RS Architecture

## Overview

LiminalQA-RS is a test framework that transforms QA from assertions into a system of collective product awareness.

## Core Principles

### 1. Bi-Temporal Data Model

Every fact in LIMINAL-DB exists along two time axes:

- **valid_time**: When the fact was true in the real world
- **tx_time**: When we learned about this fact

This allows:
- Time travel queries ("show me the state 3 days ago")
- Audit trails (when did we discover this bug?)
- Causality analysis (what led to this failure?)

### 2. LIMINAL Philosophy

```
Guidance → Co-Navigation → Inner Council → Reflection
```

#### Guidance
Test intention expressed as observables:
- What should we see in the UI?
- What API responses should we get?
- What WebSocket messages should arrive?

#### Co-Navigation
Adaptive execution:
- Automatic retries with exponential backoff
- Flexible waits (don't fail immediately)
- Time-boxed operations

#### Inner Council
Signal reconciliation:
- Collect signals from multiple sources (UI, API, WS, gRPC)
- Detect inconsistencies (UI changed but no API call?)
- Identify patterns (latency spikes, connection drops)

#### Reflection
Causality-based reporting:
- Story of what happened, not just pass/fail
- Causality trail (event A → event B → failure)
- Resonance patterns (this test flakes when...)

## Module Architecture

### liminalqa-core
Foundation types and data model:
- Entities: System, Build, Run, Test, Artifact, Signal, Resonance
- Facts: Attribute-value pairs with bi-temporal timestamps
- Types: TestStatus, SignalType, ArtifactRef, etc.

### liminalqa-db
Bi-temporal storage engine built on sled:
- Entity storage with ULID keys
- Fact storage with temporal indexes
- Query interface for timeshift and causality walks

Indexes:
- `entities`: ULID → Entity
- `facts`: FactID → Fact
- `valid_time_index`: timestamp → facts
- `tx_time_index`: timestamp → facts
- `entity_type_index`: type → entities

### liminalqa-runner
Test execution engine implementing LIMINAL philosophy:
- `Guidance`: Test intention definition
- `CoNavigator`: Adaptive execution strategies
- `InnerCouncil`: Signal reconciliation
- `Reflection`: Causality-based reporting
- `TestRunner`: Orchestration

### liminalqa-ingest
REST API server for data ingestion:
- POST /ingest/run
- POST /ingest/tests
- POST /ingest/signals
- POST /ingest/artifacts
- POST /query

Built with Axum, provides JSON API for hermetic runners.

### limctl
CLI tool for managing test runs:
- `limctl run <plan>` — Execute test plan
- `limctl collect <run-id>` — Collect artifacts
- `limctl report <run-id>` — Generate reflection report
- `limctl query <query.json>` — Query LIMINAL-DB
- `limctl list runs|tests|systems` — List entities
- `limctl init` — Initialize new project

## Data Flow

```
┌─────────────────┐
│   Test Case     │
│   (Guidance)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Test Runner    │
│ (Co-Navigator)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Inner Council   │
│ (Signals)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│   Reflection    │─────▶│  LIMINAL-DB  │
│   (Report)      │      │ (Facts)      │
└─────────────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│  Ingest API     │
│  (REST/gRPC)    │
└─────────────────┘
```

## Storage Layout

### Database Structure

```
/data/liminaldb/
├── entities        # ULID → Entity
├── facts          # FactID → Fact
├── idx_valid_time # timestamp:entity:fact → key
├── idx_tx_time    # timestamp:entity:fact → key
└── idx_entity_type# type:entity → key
```

### Artifact Structure

```
/var/liminal/runs/<run-id>/
├── plan.yaml
├── logs.ndjson
├── artifacts/
│   ├── screenshots/
│   ├── api/
│   ├── ws/
│   └── traces/
└── report/
    └── reflection.json
```

## Temporal Queries

### Timeshift Query
View the world as it was at a specific moment:

```rust
let query = TimeshiftQuery::at(
    chrono::DateTime::parse_from_rfc3339("2024-01-15T10:00:00Z")?
);
```

### Causality Walk
Trace events leading to a failure:

```
Test Failed
  ↑
API 500 Error
  ↑
Database Connection Timeout
  ↑
Network Latency Spike
```

### Resonance Detection
Identify patterns across test runs:

- Flaky tests (pass/fail inconsistency)
- Timing-dependent failures
- Environmental sensitivities
- Signal correlations

## Extensibility

### Custom Attributes
Define domain-specific attributes:

```rust
Attribute::Custom(":payment/transaction_id".to_string())
```

### Custom Observables
Add new observable types:

```rust
Observable::Custom {
    description: "Payment webhook received"
}
```

### Custom Signals
Record any system observation:

```rust
Signal {
    signal_type: SignalType::Database,
    metadata: json!({
        "query": "SELECT ...",
        "duration_ms": 150
    }),
    ...
}
```

## Future Directions

### MVP-1
- Complete bi-temporal query implementation
- HTML reflection report template
- Causality visualization

### MVP-2
- gRPC API (in addition to REST)
- Resonance map generation
- Baseline flake detection
- Pattern matching engine

### MVP-3
- LiminalOS integration (hermetic runners)
- Nix/OCI reproducible environments
- CI/CD integrations (GitHub Actions, GitLab, Jenkins)
- SBOM generation
- Anonymized resonance sharing

## Integration with LiminalOS

LiminalOS provides:
- Hermetic test execution (isolated environments)
- Reproducible builds (Nix/OCI)
- Artifact management
- Secret handling via file descriptors

LiminalQA-RS provides:
- Test philosophy and execution model
- Bi-temporal data storage
- Signal reconciliation
- Causality-based reporting

Together they form a complete testing platform with memory and awareness.
