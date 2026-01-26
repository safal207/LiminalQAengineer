//! List runs command

use anyhow::Result;
use comfy_table::Table;
use liminalqa_db::PostgresStorage;

pub async fn execute(db: &PostgresStorage) -> Result<()> {
    println!("📋 Listing recent runs...");

    let runs = db.get_recent_runs(20).await?;

    let mut table = Table::new();
    table.set_header(vec!["ID", "Plan", "Status", "Started At", "Duration"]);

    for run in runs {
        table.add_row(vec![
            run.id,
            run.plan_name,
            run.status,
            run.started_at.to_string(),
            run.duration_ms
                .map(|d| format!("{}ms", d))
                .unwrap_or_default(),
        ]);
    }

    println!("{table}");

    Ok(())
}
