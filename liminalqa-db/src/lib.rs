//! LIMINAL-DB — Bi-temporal storage engine (PostgreSQL Backend)

pub mod models;
pub mod postgres;
pub mod query;

pub use models::*;
pub use postgres::PostgresStorage;
pub use query::{Query, QueryResult};

use anyhow::Result;

/// Initialize a new LIMINAL-DB instance (PostgreSQL)
pub async fn open(database_url: &str) -> Result<PostgresStorage> {
    PostgresStorage::new(database_url).await
}
