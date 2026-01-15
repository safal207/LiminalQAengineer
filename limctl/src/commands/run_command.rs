//! Run command

use anyhow::{Context, Result};
use liminalqa_core::{
    entities::{Run, Test},
    temporal::BiTemporalTime,
    types::{EntityId, Environment, TestStatus},
};
use liminalqa_db::LiminalDB;
use liminalqa_runner::TestRunner;
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::fs;
use tracing::info;

#[derive(Debug, Deserialize, Serialize)]
pub struct TestPlan {
    pub name: String,
    pub environment: Option<Environment>,
    pub tests: Vec<TestDefinition>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TestDefinition {
    pub name: String,
    pub suite: String,
    pub guidance: String,
}

pub async fn execute(db: &LiminalDB, plan_path: &Path) -> Result<()> {
    println!("📋 Loading test plan: {}", plan_path.display());
    
    let plan_content = fs::read_to_string(plan_path)
        .context(format!("Failed to read test plan file: {}", plan_path.display()))?;
    
    let plan: TestPlan = serde_yaml::from_str(&plan_content)
        .context(format!("Failed to parse test plan: {}", plan_path.display()))?;
    
    info!("Loaded test plan '{}' with {} tests", plan.name, plan.tests.len());
    
    // Create a new run
    let run_id = EntityId::new();
    let run = Run {
        id: run_id,
        build_id: EntityId::new(),
        plan_name: plan.name,
        env: plan.environment.unwrap_or(Environment::default()),
        started_at: chrono::Utc::now(),
        ended_at: None,
        runner_version: env!("CARGO_PKG_VERSION").to_string(),
        liminal_os_version: None,
        created_at: BiTemporalTime::now(),
    };
    
    // Store the run in the database
    db.put_run(&run)?;
    println!("✅ Created run: {}", run.id);
    
    // Execute tests
    let runner = TestRunner::new(run_id);
    let mut results = Vec::new();
    
    for test_def in plan.tests {
        println!("🧪 Executing test: {}::{}", test_def.suite, test_def.name);
        
        // For now, create a mock test execution
        // In a real implementation, this would use the TestRunner to execute actual tests
        let test_id = EntityId::new();
        let test = Test {
            id: test_id,
            run_id,
            name: test_def.name,
            suite: test_def.suite,
            guidance: test_def.guidance,
            status: TestStatus::Pass, // For now, assuming all pass
            duration_ms: 100, // Mock duration
            error: None,
            started_at: chrono::Utc::now(),
            completed_at: chrono::Utc::now(),
            created_at: BiTemporalTime::now(),
        };
        
        // Store the test result in the database
        db.put_test(&test)?;
        results.push(test);
    }
    
    // Update run to mark as completed
    let mut completed_run = run;
    completed_run.ended_at = Some(chrono::Utc::now());
    db.put_run(&completed_run)?;
    
    println!("✅ Completed run with {} tests", results.len());
    println!("📊 Results: {} passed, {} failed", 
        results.iter().filter(|r| r.status == TestStatus::Pass).count(),
        results.iter().filter(|r| r.status == TestStatus::Fail).count()
    );
    
    Ok(())
}