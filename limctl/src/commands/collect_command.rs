//! Collect command

use anyhow::{Context, Result};
use liminalqa_core::{
    entities::{Artifact, EntityType, Run, Signal, Test},
    types::EntityId,
};
use liminalqa_db::LiminalDB;
use std::fs;
use std::path::PathBuf;

pub async fn execute(db: &LiminalDB, run_id: &str) -> Result<()> {
    println!("📦 Collecting artifacts for run: {}", run_id);

    // Convert run_id string to EntityId
    let entity_id = EntityId::from_string(run_id)
        .context("Invalid run ID format")?;

    // Get the run from the database
    let run: Option<Run> = db.get_entity(entity_id)?;
    
    if let Some(run) = run {
        println!("   Plan: {}", run.plan_name);
        println!("   Started: {}", run.started_at.format("%Y-%m-%d %H:%M:%S UTC"));
        
        // Get all artifacts for this run
        let all_artifact_ids = db.get_entities_by_type(EntityType::Artifact)?;
        let run_artifacts: Vec<Artifact> = all_artifact_ids
            .into_iter()
            .filter_map(|id| {
                if let Ok(Some(artifact)) = db.get_entity::<Artifact>(id) {
                    if artifact.run_id == entity_id {
                        Some(artifact)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .collect();

        // Get all signals for this run
        let all_signal_ids = db.get_entities_by_type(EntityType::Signal)?;
        let run_signals: Vec<Signal> = all_signal_ids
            .into_iter()
            .filter_map(|id| {
                if let Ok(Some(signal)) = db.get_entity::<Signal>(id) {
                    if signal.run_id == entity_id {
                        Some(signal)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .collect();

        // Get all tests for this run
        let all_test_ids = db.get_entities_by_type(EntityType::Test)?;
        let run_tests: Vec<Test> = all_test_ids
            .into_iter()
            .filter_map(|id| {
                if let Ok(Some(test)) = db.get_entity::<Test>(id) {
                    if test.run_id == entity_id {
                        Some(test)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .collect();

        // Create a directory for collected artifacts
        let artifacts_dir = PathBuf::from("collected_artifacts").join(run_id);
        fs::create_dir_all(&artifacts_dir)
            .context("Failed to create artifacts directory")?;

        // Save run information
        let run_info_path = artifacts_dir.join("run.json");
        fs::write(&run_info_path, serde_json::to_string_pretty(&run)?)
            .context("Failed to save run information")?;
        println!("   Saved run information to: {}", run_info_path.display());

        // Save tests information
        let tests_info_path = artifacts_dir.join("tests.json");
        fs::write(&tests_info_path, serde_json::to_string_pretty(&run_tests)?)
            .context("Failed to save tests information")?;
        println!("   Saved {} test(s) information to: {}", run_tests.len(), tests_info_path.display());

        // Save signals information
        let signals_info_path = artifacts_dir.join("signals.json");
        fs::write(&signals_info_path, serde_json::to_string_pretty(&run_signals)?)
            .context("Failed to save signals information")?;
        println!("   Saved {} signal(s) information to: {}", run_signals.len(), signals_info_path.display());

        // Save artifacts information
        let artifacts_info_path = artifacts_dir.join("artifacts.json");
        fs::write(&artifacts_info_path, serde_json::to_string_pretty(&run_artifacts)?)
            .context("Failed to save artifacts information")?;
        println!("   Saved {} artifact(s) information to: {}", run_artifacts.len(), artifacts_info_path.display());

        // Create a summary file
        let summary_path = artifacts_dir.join("summary.txt");
        let summary = format!(
            "Run Summary\n===========\nID: {}\nPlan: {}\nStarted: {}\nEnded: {}\n\nArtifacts:\n- {} tests\n- {} signals\n- {} artifacts\n",
            run.id,
            run.plan_name,
            run.started_at,
            run.ended_at.map_or_else(|| "Not completed".to_string(), |t| t.to_string()),
            run_tests.len(),
            run_signals.len(),
            run_artifacts.len()
        );
        fs::write(&summary_path, summary)
            .context("Failed to save summary")?;
        println!("   Saved summary to: {}", summary_path.display());

        println!("✅ Collection completed. Artifacts saved to: {}", artifacts_dir.display());
        println!("📁 Directory contains {} files", fs::read_dir(&artifacts_dir)?.count());

        Ok(())
    } else {
        println!("❌ Run not found: {}", run_id);
        anyhow::bail!("Run not found: {}", run_id);
    }
}