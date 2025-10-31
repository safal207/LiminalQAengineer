//! Index management for efficient queries

use anyhow::Result;
use chrono::{DateTime, Utc};

/// Index key builder for temporal queries
pub struct IndexKey;

impl IndexKey {
    /// Build a key for valid_time index
    pub fn valid_time(timestamp: DateTime<Utc>, entity_id: &str, fact_id: &str) -> String {
        format!("{}:{}:{}", timestamp.timestamp_millis(), entity_id, fact_id)
    }

    /// Build a key for tx_time index
    pub fn tx_time(timestamp: DateTime<Utc>, entity_id: &str, fact_id: &str) -> String {
        format!("{}:{}:{}", timestamp.timestamp_millis(), entity_id, fact_id)
    }

    /// Build a key for entity_type index
    pub fn entity_type(entity_type: &str, entity_id: &str) -> String {
        format!("{}:{}", entity_type, entity_id)
    }
}

/// Parse timestamp from index key
pub fn parse_timestamp_from_key(key: &str) -> Result<i64> {
    let parts: Vec<&str> = key.split(':').collect();
    if parts.is_empty() {
        anyhow::bail!("Invalid index key format");
    }
    parts[0]
        .parse::<i64>()
        .map_err(|e| anyhow::anyhow!("Failed to parse timestamp: {}", e))
}
