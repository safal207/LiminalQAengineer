//! List systems command

use anyhow::Result;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use liminalqa_core::entities::{EntityType, System};
use liminalqa_db::LiminalDB;

pub async fn execute(db: &LiminalDB) -> Result<()> {
    println!("🖥️  Listing all systems...\n");

    let system_ids = db.get_entities_by_type(EntityType::System)?;

    if system_ids.is_empty() {
        println!("No systems found.");
        return Ok(());
    }

    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec!["System ID", "Name", "Version", "Repository"]);

    for system_id in system_ids {
        let system: Option<System> = db.get_entity(system_id)?;
        if let Some(s) = system {
            table.add_row(vec![
                s.id.to_string(),
                s.name,
                s.version,
                s.repository.unwrap_or_else(|| "N/A".to_string()),
            ]);
        }
    }

    println!("{table}");
    Ok(())
}
