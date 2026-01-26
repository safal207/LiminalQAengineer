//! List tests command

use anyhow::Result;
use comfy_table::Table;
use liminalqa_db::PostgresStorage;

pub async fn execute(db: &PostgresStorage, run_id: &str) -> Result<()> {
    println!("📋 Listing tests for run: {}", run_id);

    let tests = db.get_tests_by_run(run_id).await?;

    let mut table = Table::new();
    table.set_header(vec!["Suite", "Name", "Status", "Duration"]);

    for test in tests {
        table.add_row(vec![
            test.suite,
            test.name,
            test.status,
            format!("{}ms", test.duration_ms),
        ]);
    }

    println!("{table}");

    Ok(())
}
