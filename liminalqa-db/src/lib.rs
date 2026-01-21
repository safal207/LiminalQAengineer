//! LIMINAL-DB — Bi-temporal storage engine
//!
//! Features:
//! - Two temporal axes: valid_time (when fact was true) and tx_time (when we learned)
//! - Timeshift queries (view world at any point in time)
//! - Causality walks (trace root causes)
//! - Efficient indexing for time-based queries

pub mod index;
pub mod query;
pub mod storage;

pub use query::{Query, QueryResult};
pub use storage::LiminalDB;

use anyhow::Result;

/// Initialize a new LIMINAL-DB instance
pub fn open<P: AsRef<std::path::Path>>(path: P) -> Result<LiminalDB> {
    LiminalDB::open(path)
}
