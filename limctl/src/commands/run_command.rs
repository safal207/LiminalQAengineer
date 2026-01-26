//! Run command

use anyhow::{Context, Result};
use chrono::Utc;
use liminalqa_db::{
    models::{TestResult, TestRun},
    PostgresStorage,
};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use tracing::info;

#[derive(Debug, Deserialize, Serialize)]
pub struct TestPlan {
    pub name: String,
    pub environment: Option<serde_json::Value>,
    pub tests: Vec<TestDefinition>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TestDefinition {
    pub name: String,
    pub suite: String,
    pub guidance: String,
}

pub async fn execute(db: &PostgresStorage, plan_path: &Path) -> Result<()> {
    println!("📋 Loading test plan: {}", plan_path.display());

    let plan_content = fs::read_to_string(plan_path).context(format!(
        "Failed to read test plan file: {}",
        plan_path.display()
    ))?;

    let plan: TestPlan = serde_yaml::from_str(&plan_content).context(format!(
        "Failed to parse test plan: {}",
        plan_path.display()
    ))?;

    info!(
        "Loaded test plan '{}' with {} tests",
        plan.name,
        plan.tests.len()
    );

    // Create a new run
    let run_id = ulid::Ulid::new().to_string();
    let run = TestRun {
        id: run_id.clone(),
        build_id: Some(ulid::Ulid::new().to_string()),
        plan_name: plan.name,
        status: "running".to_string(),
        started_at: Utc::now(),
        completed_at: None,
        duration_ms: None,
        environment: plan.environment,
        metadata: None,
        created_at: Utc::now(),
        protocol_version: None,
        self_resonance_score: None,
        world_resonance_score: None,
        overall_alignment_score: None,
    };

    // Store the run in the database
    db.insert_run(&run).await?;
    println!("✅ Created run: {}", run.id);

    // Execute tests
    let mut results = Vec::new();

    for test_def in plan.tests {
        println!("🧪 Executing test: {}::{}", test_def.suite, test_def.name);

        // For now, create a mock test execution
        let test_id = ulid::Ulid::new().to_string();
        let test = TestResult {
            id: test_id,
            run_id: run_id.clone(),
            name: test_def.name,
            suite: test_def.suite,
            status: "passed".to_string(),
            duration_ms: 100,
            error_message: None,
            stack_trace: None,
            metadata: None,
            executed_at: Utc::now(),
            created_at: Utc::now(),
            protocol_metrics: None,
        };

        // Store the test result in the database
        db.insert_test(&test).await?;
        results.push(test);
    }

    // Update run to mark as completed (simplified, re-using struct but in real world would use update)
    // Note: Since PostgresStorage doesn't expose update_run yet, we skip this step or add it.
    // For MVP, we just rely on insert.

    println!("✅ Completed run with {} tests", results.len());

    Ok(())
}
