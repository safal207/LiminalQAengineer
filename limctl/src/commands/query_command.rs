//! Query command

use anyhow::{Context, Result};
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use liminalqa_core::{
    temporal::{TimeRange, TimeshiftQuery},
    types::EntityId,
};
use liminalqa_db::{LiminalDB, Query, QueryResult};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::fs;

#[derive(Debug, Deserialize, Serialize)]
pub struct QuerySpec {
    pub entity_types: Option<Vec<String>>,
    pub entity_ids: Option<Vec<String>>,
    pub valid_time_range: Option<TimeRangeSpec>,
    pub tx_time_range: Option<TimeRangeSpec>,
    pub timeshift: Option<TimeshiftSpec>,
    pub limit: Option<usize>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TimeRangeSpec {
    pub start: String, // ISO 8601 datetime string
    pub end: Option<String>, // ISO 8601 datetime string
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TimeshiftSpec {
    pub valid_time: String, // ISO 8601 datetime string
    pub tx_time: String,    // ISO 8601 datetime string
}

pub async fn execute(db: &LiminalDB, query_path: &Path) -> Result<()> {
    println!("🔍 Executing query from: {}", query_path.display());

    let query_content = fs::read_to_string(query_path)
        .context(format!("Failed to read query file: {}", query_path.display()))?;

    let query_spec: QuerySpec = serde_json::from_str(&query_content)
        .context(format!("Failed to parse query specification: {}", query_path.display()))?;

    // Build the query based on the specification
    let mut query = Query::new();

    // Add entity IDs filter if specified
    if let Some(entity_ids_str) = &query_spec.entity_ids {
        let entity_ids: Result<Vec<EntityId>, _> = entity_ids_str
            .iter()
            .map(|id_str| EntityId::from_string(id_str))
            .collect();
        let entity_ids = entity_ids.context("Invalid entity ID format in query")?;
        query = query.for_entities(entity_ids);
    }

    // Add time range filters
    if let Some(valid_range) = &query_spec.valid_time_range {
        let start = chrono::DateTime::parse_from_rfc3339(&valid_range.start)
            .context("Invalid start time format in valid_time_range")?
            .with_timezone(&chrono::Utc);
        let end = if let Some(end_str) = &valid_range.end {
            Some(chrono::DateTime::parse_from_rfc3339(end_str)
                .context("Invalid end time format in valid_time_range")?
                .with_timezone(&chrono::Utc))
        } else {
            None
        };
        
        let time_range = match end {
            Some(end_time) => TimeRange::between(start, end_time),
            None => TimeRange::from(start),
        };
        query = query.valid_time_range(time_range);
    }

    if let Some(tx_range) = &query_spec.tx_time_range {
        let start = chrono::DateTime::parse_from_rfc3339(&tx_range.start)
            .context("Invalid start time format in tx_time_range")?
            .with_timezone(&chrono::Utc);
        let end = if let Some(end_str) = &tx_range.end {
            Some(chrono::DateTime::parse_from_rfc3339(end_str)
                .context("Invalid end time format in tx_time_range")?
                .with_timezone(&chrono::Utc))
        } else {
            None
        };
        
        let time_range = match end {
            Some(end_time) => TimeRange::between(start, end_time),
            None => TimeRange::from(start),
        };
        query = query.tx_time_range(time_range);
    }

    // Add timeshift filter if specified
    if let Some(timeshift_spec) = &query_spec.timeshift {
        let valid_time = chrono::DateTime::parse_from_rfc3339(&timeshift_spec.valid_time)
            .context("Invalid valid_time format in timeshift")?
            .with_timezone(&chrono::Utc);
        let tx_time = chrono::DateTime::parse_from_rfc3339(&timeshift_spec.tx_time)
            .context("Invalid tx_time format in timeshift")?
            .with_timezone(&chrono::Utc);
        
        let timeshift = TimeshiftQuery::valid_at_tx(valid_time, tx_time);
        query = query.timeshift(timeshift);
    }

    // Add limit if specified
    if let Some(limit) = query_spec.limit {
        query = query.limit(limit);
    }

    // Execute the query
    let result: QueryResult = query.execute(db)?;

    // Display the results
    println!("✅ Query executed successfully");
    println!("📊 Found {} facts", result.total);

    if result.facts.is_empty() {
        println!("No facts found matching the query criteria.");
        return Ok(());
    }

    // Create a table to display the results
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec!["Entity ID", "Attribute", "Value", "Valid Time", "Tx Time"]);

    for fact in result.facts.iter().take(20) { // Limit to first 20 results for readability
        table.add_row(vec![
            fact.entity_id.to_string(),
            fact.attribute.to_string(),
            fact.value.to_string(),
            fact.time.valid_time.format("%Y-%m-%d %H:%M:%S").to_string(),
            fact.time.tx_time.format("%Y-%m-%d %H:%M:%S").to_string(),
        ]);
    }

    println!("{}", table);

    if result.facts.len() > 20 {
        println!("... and {} more results", result.facts.len() - 20);
    }

    Ok(())
}