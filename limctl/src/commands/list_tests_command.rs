//! List tests command

use anyhow::{Context, Result};
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use liminalqa_core::{entities::Test, types::EntityId};
use liminalqa_db::LiminalDB;

pub async fn execute(db: &LiminalDB, run_id_str: &str) -> Result<()> {
    let run_id = EntityId::from_string(run_id_str)
        .context("Invalid run ID format")?;

    println!("📋 Listing tests for run: {}\n", run_id);

    // TODO: Implement getting tests by run_id
    println!("⚠️  List tests command not yet implemented");
    println!("   Need to add index for run_id → tests");

    Ok(())
}
