//! List runs command

use anyhow::Result;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use liminalqa_core::entities::{EntityType, Run};
use liminalqa_db::LiminalDB;

pub async fn execute(db: &LiminalDB) -> Result<()> {
    println!("📋 Listing all runs...\n");

    let run_ids = db.get_entities_by_type(EntityType::Run)?;

    if run_ids.is_empty() {
        println!("No runs found.");
        return Ok(());
    }

    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec!["Run ID", "Plan", "Started", "Status"]);

    for run_id in run_ids {
        let run: Option<Run> = db.get_entity(run_id)?;
        if let Some(r) = run {
            table.add_row(vec![
                r.id.to_string(),
                r.plan_name,
                r.started_at.format("%Y-%m-%d %H:%M:%S").to_string(),
                if r.ended_at.is_some() {
                    "Completed"
                } else {
                    "Running"
                }
                .to_string(),
            ]);
        }
    }

    println!("{table}");
    Ok(())
}
