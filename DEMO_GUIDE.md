# LiminalQAengineer Demo Guide

This guide explains how to demonstrate the capabilities of LiminalQAengineer using the demo application.

## Project Status

Currently, the project has some compilation issues on Windows due to linker problems with the GNU toolchain. However, the architecture and concepts are fully implemented and ready for demonstration.

## Demo Application

The demo application (`demo-app`) showcases several key features:

1. **Health endpoint** - `/health` for basic connectivity
2. **Slow endpoint** - `/slow` with configurable delays
3. **Flaky endpoint** - `/flaky` with probabilistic errors (20% failure rate)
4. **User endpoints** - `/users` for CRUD operations
5. **Error simulation** - `/users/2` returns 404 to demonstrate error detection

## LiminalQA Capabilities Demonstrated

### 1. Bi-Temporal Data Model
- **valid_time**: When the fact was true in the real world
- **transaction_time**: When we learned about the fact
- This allows for "timeshift queries" to see the system state at any point in time

### 2. LIMINAL Philosophy
- **Guidance**: Define test intentions
- **Co-Navigation**: Adaptive execution with retries and flexible waits
- **Inner Council**: Reconcile signals from multiple sources (UI/API/WS/gRPC)
- **Reflection**: Generate causality-based reports

### 3. Causality Analysis
- Track root causes of failures
- Understand relationships between tests and system behavior
- Identify patterns of instability ("resonances")

### 4. Resonance Detection
- Identify flaky tests and unstable system components
- Pattern recognition for system instability
- Predictive analysis of potential issues

## How to Run the Demo (Linux/macOS)

If running on Linux or macOS:

1. Navigate to the demo-app directory:
   ```bash
   cd demo-app
   npm install
   npm start
   ```

2. In another terminal, initialize a LiminalQA project:
   ```bash
   cd LiminalQAengineer
   cargo run --bin limctl -- init demo-project
   ```

3. Run tests against the demo app:
   ```bash
   cargo run --bin limctl -- run ../demo-app/liminal-test-plan.yaml
   ```

4. View results:
   ```bash
   cargo run --bin limctl -- list runs
   cargo run --bin limctl -- report <run-id> --format html --output reports/demo.html
   ```

## How to Run the Demo (Alternative Method)

Due to Windows compilation issues, an alternative approach is to demonstrate the concepts:

1. Show the architecture and design patterns in the code
2. Demonstrate the CLI command implementations we've created
3. Explain the bi-temporal model with examples
4. Show the test plan structure and how it maps to the philosophy

## Key Files to Highlight

- `limctl/src/commands/run_command.rs` - Test execution logic
- `limctl/src/commands/report_command.rs` - Report generation in multiple formats
- `limctl/src/commands/query_command.rs` - Bi-temporal query capabilities
- `limctl/src/commands/collect_command.rs` - Artifact collection
- `liminalqa-db/src/query.rs` - Bi-temporal query implementation
- `demo-app/server.js` - Demo application with intentional behaviors

## Value Proposition

LiminalQAengineer transforms QA from a collection of assertions into a system of collective awareness. It enables teams to:

- Understand the causality behind test failures
- Detect system instabilities and flakiness patterns
- Maintain a temporal view of system behavior
- Create shared knowledge about system quality

## Next Steps for Production Readiness

Based on the ROADMAP.md:
- Resolve Windows compilation issues
- Improve test coverage
- Enhance observability features
- Complete CLI command implementations
- Add security features and proper error handling