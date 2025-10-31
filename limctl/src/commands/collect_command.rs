//! Collect command

use anyhow::Result;
use liminalqa_db::LiminalDB;

pub async fn execute(db: &LiminalDB, run_id: &str) -> Result<()> {
    println!("📦 Collecting artifacts for run: {}", run_id);

    // TODO: Implement artifact collection
    println!("⚠️  Collect command not yet implemented");
    println!("   Will gather screenshots, logs, traces from /var/liminal/runs/{}", run_id);

    Ok(())
}
