//! Init command

use anyhow::{Context, Result};
use std::fs;
use std::path::Path;

pub async fn execute(directory: &Path) -> Result<()> {
    println!(
        "🚀 Initializing LiminalQA project in: {}",
        directory.display()
    );

    // Create directory structure
    let dirs = [
        "tests",
        "plans",
        "data/liminaldb",
        "data/artifacts",
        "reports",
    ];

    for dir in dirs {
        let path = directory.join(dir);
        fs::create_dir_all(&path)
            .context(format!("Failed to create directory: {}", path.display()))?;
        println!("   ✓ Created {}", dir);
    }

    // Create example plan
    let example_plan = "# LiminalQA Test Plan Example
name: example-plan
version: 1.0

system:
  name: example-app
  version: 1.0.0

tests:
  - name: test_login
    suite: auth
    guidance: User should be able to log in with valid credentials
    observables:
      - type: ui_visible
        selector: login-button
      - type: api_status
        endpoint: /api/auth/login
        status: 200

  - name: test_dashboard_load
    suite: ui
    guidance: Dashboard should load and display user data
    observables:
      - type: ui_visible
        selector: dashboard
      - type: api_status
        endpoint: /api/user/me
        status: 200
";

    let plan_path = directory.join("plans/example.yaml");
    fs::write(&plan_path, example_plan).context("Failed to write example plan")?;
    println!("   ✓ Created example plan: plans/example.yaml");

    // Create README
    let readme = r#"# LiminalQA Project

This project uses LiminalQA-RS for testing with bi-temporal observability.

## Structure

- `tests/` — Test implementations
- `plans/` — Test plans (YAML)
- `data/liminaldb/` — Bi-temporal database
- `data/artifacts/` — Screenshots, logs, traces
- `reports/` — Reflection reports

## Quick Start

```bash
# Run tests
limctl run plans/example.yaml

# List runs
limctl list runs

# Generate report
limctl report <run-id> --format html --output reports/latest.html
```

## Philosophy

LiminalQA follows the Guidance → Co-Navigation → Council → Reflection philosophy:

- **Guidance**: Define test intentions
- **Co-Navigation**: Adaptive execution with retries
- **Inner Council**: Signal reconciliation (UI/API/WS/gRPC)
- **Reflection**: Causality-based reporting

## Learn More

Visit https://github.com/safal207/LiminalQAengineer
"#;

    let readme_path = directory.join("README.md");
    fs::write(&readme_path, readme).context("Failed to write README")?;
    println!("   ✓ Created README.md");

    println!("\n✨ LiminalQA project initialized successfully!");
    println!("   Next: limctl run plans/example.yaml");

    Ok(())
}
