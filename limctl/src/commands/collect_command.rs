//! Collect command

use anyhow::Result;
use liminalqa_db::PostgresStorage;

pub async fn execute(_db: &PostgresStorage, run_id: &str) -> Result<()> {
    println!("📥 Collecting artifacts for run: {}", run_id);

    // Stub implementation for Phase 4
    println!("Artifact collection not yet implemented for PostgreSQL backend");

    Ok(())
}
