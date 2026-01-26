//! List systems command

use anyhow::Result;
use liminalqa_db::PostgresStorage;

pub async fn execute(_db: &PostgresStorage) -> Result<()> {
    println!("📋 Listing systems...");
    println!("System listing not yet implemented for PostgreSQL backend");
    Ok(())
}
