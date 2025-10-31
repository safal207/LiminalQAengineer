# LiminalQA-RS Quick Start

This guide will help you get started with LiminalQA-RS in 5 minutes.

## Prerequisites

- Rust 1.70+ (install from https://rustup.rs/)
- Basic understanding of testing concepts

## Installation

```bash
# Clone the repository
git clone https://github.com/safal207/LiminalQAengineer
cd LiminalQAengineer

# Build the project
cargo build --release

# Run tests to verify installation
cargo test
```

## Your First Test

### 1. Initialize a project

```bash
cargo run --bin limctl -- init my-qa-project
cd my-qa-project
```

This creates the following structure:
```
my-qa-project/
├── tests/          # Test implementations
├── plans/          # Test plans (YAML)
├── data/           # LIMINAL-DB and artifacts
└── reports/        # Generated reports
```

### 2. Create a test

Create `tests/login_test.rs`:

```rust
use liminalqa_runner::*;
use async_trait::async_trait;
use anyhow::Result;

struct LoginTest;

#[async_trait]
impl TestCase for LoginTest {
    fn name(&self) -> &str { "test_login" }
    fn suite(&self) -> &str { "auth" }

    fn guidance(&self) -> Guidance {
        Guidance::new("User should be able to log in with valid credentials")
            .with_observable(Observable::UiVisible {
                selector: "#login-button".to_string()
            })
            .with_observable(Observable::ApiStatus {
                endpoint: "/api/auth/login".to_string(),
                status: 200
            })
    }

    async fn execute(
        &self,
        navigator: &CoNavigator,
        council: &mut InnerCouncil
    ) -> Result<()> {
        // Your test implementation
        Ok(())
    }
}
```

### 3. Run the ingest server

In one terminal:
```bash
LIMINAL_DB_PATH=./data/liminaldb cargo run --bin liminalqa-ingest
```

The server starts on http://localhost:8080

### 4. Execute tests

In another terminal:
```bash
cargo run --bin limctl -- run plans/example.yaml
```

### 5. View results

```bash
# List all runs
cargo run --bin limctl -- list runs

# Generate HTML report
cargo run --bin limctl -- report <run-id> --format html --output reports/latest.html

# Open the report
open reports/latest.html  # macOS
xdg-open reports/latest.html  # Linux
```

## Understanding the Philosophy

### Guidance
Define WHAT you want to observe, not HOW to check it:
```rust
Guidance::new("Dashboard should load user data")
    .with_observable(Observable::UiVisible { selector: ".dashboard" })
    .with_observable(Observable::ApiStatus { endpoint: "/api/user", status: 200 })
```

### Co-Navigation
Tests adapt to reality with retries and flexible waits:
```rust
navigator.execute_with_retry(|| async {
    // API call that might need retries
    call_api().await
}).await?;
```

### Inner Council
Collect signals from all layers:
```rust
council.record(ui_signal);
council.record(api_signal);
council.record(ws_signal);

// Council reconciles them automatically
let reconciliation = council.reconcile();
```

### Reflection
Get causality-based reports, not just pass/fail:
```
Test Failed
  ↑ API returned 500
  ↑ Database connection timeout
  ↑ Network latency spike
```

## Next Steps

1. **Write Real Tests**: Adapt the example to your application
2. **Explore LIMINAL-DB**: Query bi-temporal data
3. **Set Up CI**: Integrate with GitHub Actions, GitLab, etc.
4. **Generate Reports**: Create resonance maps and causality trails

## CLI Reference

```bash
# Initialize project
limctl init [directory]

# Run test plan
limctl run <plan.yaml>

# Collect artifacts
limctl collect <run-id>

# Generate report
limctl report <run-id> --format html|json|markdown

# Query database
limctl query <query.json>

# List entities
limctl list runs
limctl list tests <run-id>
limctl list systems
```

## Environment Variables

- `LIMINAL_DB_PATH`: Path to LIMINAL-DB (default: `./data/liminaldb`)
- `RUST_LOG`: Logging level (error|warn|info|debug|trace)

## Common Issues

### "Database locked"
Only one process can write to LIMINAL-DB at a time. Make sure the ingest server is the only writer.

### "Connection refused"
Make sure the ingest server is running on port 8080.

### Compilation errors
Ensure you're using Rust 1.70+:
```bash
rustc --version
rustup update
```

## Getting Help

- 📖 Read [ARCHITECTURE.md](./ARCHITECTURE.md) for deep dive
- 🐛 Report issues at https://github.com/safal207/LiminalQAengineer/issues
- 💬 Discuss at https://github.com/safal207/LiminalQAengineer/discussions

---

**Welcome to LiminalQA — where tests have memory and awareness! 🧠**
