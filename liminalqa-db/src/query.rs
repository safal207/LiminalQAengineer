//! Query interface for bi-temporal data

use anyhow::Result;
use liminalqa_core::{
    temporal::{TimeRange, TimeshiftQuery},
    types::EntityId,
};
use serde::{Deserialize, Serialize};

use crate::storage::LiminalDB;

/// Query builder
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Query {
    pub entity_ids: Option<Vec<EntityId>>,
    pub valid_time_range: Option<TimeRange>,
    pub tx_time_range: Option<TimeRange>,
    pub timeshift: Option<TimeshiftQuery>,
    pub limit: Option<usize>,
}

impl Query {
    pub fn new() -> Self {
        Self {
            entity_ids: None,
            valid_time_range: None,
            tx_time_range: None,
            timeshift: None,
            limit: None,
        }
    }

    pub fn for_entities(mut self, ids: Vec<EntityId>) -> Self {
        self.entity_ids = Some(ids);
        self
    }

    pub fn valid_time_range(mut self, range: TimeRange) -> Self {
        self.valid_time_range = Some(range);
        self
    }

    pub fn tx_time_range(mut self, range: TimeRange) -> Self {
        self.tx_time_range = Some(range);
        self
    }

    pub fn timeshift(mut self, ts: TimeshiftQuery) -> Self {
        self.timeshift = Some(ts);
        self
    }

    pub fn limit(mut self, n: usize) -> Self {
        self.limit = Some(n);
        self
    }

    /// Execute the query against a database
    pub fn execute(&self, db: &LiminalDB) -> Result<QueryResult> {
        // Step 1: Get candidate facts based on primary filter
        let mut facts = if let Some(ref entity_ids) = self.entity_ids {
            db.scan_facts_by_entities(entity_ids)?
        } else if let Some(ref vt_range) = self.valid_time_range {
            let start_ms = vt_range.start.timestamp_millis();
            let end_ms = vt_range.end.map(|dt| dt.timestamp_millis());
            db.scan_facts_by_valid_time(start_ms, end_ms)?
        } else {
            // No specific filter, scan all
            db.scan_facts()?
        };

        // Step 2: Apply additional filters
        if let Some(ref vt_range) = self.valid_time_range {
            facts.retain(|f| vt_range.contains(f.time.valid_time));
        }

        if let Some(ref tx_range) = self.tx_time_range {
            facts.retain(|f| tx_range.contains(f.time.tx_time));
        }

        if let Some(ref timeshift) = self.timeshift {
            facts.retain(|f| {
                f.time.valid_time <= timeshift.valid_time
                    && f.time.tx_time <= timeshift.tx_time
            });
        }

        // Step 3: Apply limit
        if let Some(limit) = self.limit {
            facts.truncate(limit);
        }

        Ok(QueryResult::new(facts))
    }
}

impl Default for Query {
    fn default() -> Self {
        Self::new()
    }
}

/// Query result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryResult {
    pub facts: Vec<liminalqa_core::facts::Fact>,
    pub total: usize,
}

impl QueryResult {
    pub fn new(facts: Vec<liminalqa_core::facts::Fact>) -> Self {
        let total = facts.len();
        Self { facts, total }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use liminalqa_core::{
        facts::{Attribute, Fact},
        temporal::{BiTemporalTime, TimeRange, TimeshiftQuery},
        types::EntityId,
    };
    use tempfile::TempDir;

    fn create_test_db() -> Result<(TempDir, LiminalDB)> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;
        Ok((temp_dir, db))
    }

    fn create_test_fact(entity_id: EntityId, attribute: Attribute, value: i32, minutes_ago: i64) -> Fact {
        let time = Utc::now() - chrono::Duration::minutes(minutes_ago);
        Fact::with_time(
            entity_id,
            attribute,
            serde_json::json!(value),
            BiTemporalTime::with_valid_time(time),
        )
    }

    fn create_test_fact_with_tx_time(
        entity_id: EntityId,
        attribute: Attribute,
        value: i32,
        valid_mins_ago: i64,
        tx_mins_ago: i64,
    ) -> Fact {
        let valid_time = Utc::now() - chrono::Duration::minutes(valid_mins_ago);
        let tx_time = Utc::now() - chrono::Duration::minutes(tx_mins_ago);
        Fact::with_time(
            entity_id,
            attribute,
            serde_json::json!(value),
            BiTemporalTime::with_times(valid_time, tx_time),
        )
    }

    #[test]
    fn test_query_all_facts() -> Result<()> {
        let (_dir, db) = create_test_db()?;
        let entity1 = EntityId::new();
        let entity2 = EntityId::new();

        // Insert test facts
        db.put_fact(&create_test_fact(entity1, Attribute::TestStatus, 1, 10))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestDuration, 100, 5))?;
        db.put_fact(&create_test_fact(entity2, Attribute::TestStatus, 2, 3))?;

        // Query all facts
        let query = Query::new();
        let result = query.execute(&db)?;

        assert_eq!(result.total, 3);
        assert_eq!(result.facts.len(), 3);

        Ok(())
    }

    #[test]
    fn test_query_by_entity_ids() -> Result<()> {
        let (_dir, db) = create_test_db()?;
        let entity1 = EntityId::new();
        let entity2 = EntityId::new();

        db.put_fact(&create_test_fact(entity1, Attribute::TestStatus, 1, 10))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestDuration, 100, 5))?;
        db.put_fact(&create_test_fact(entity2, Attribute::TestStatus, 2, 3))?;

        // Query facts for entity1 only
        let query = Query::new().for_entities(vec![entity1]);
        let result = query.execute(&db)?;

        assert_eq!(result.total, 2);
        assert!(result.facts.iter().all(|f| f.entity_id == entity1));

        Ok(())
    }

    #[test]
    fn test_query_with_limit() -> Result<()> {
        let (_dir, db) = create_test_db()?;
        let entity1 = EntityId::new();

        db.put_fact(&create_test_fact(entity1, Attribute::TestStatus, 1, 10))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestDuration, 100, 5))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestError, 3, 3))?;

        // Query with limit
        let query = Query::new().limit(2);
        let result = query.execute(&db)?;

        assert_eq!(result.total, 2);
        assert_eq!(result.facts.len(), 2);

        Ok(())
    }

    #[test]
    fn test_query_with_valid_time_range() -> Result<()> {
        let (_dir, db) = create_test_db()?;
        let entity1 = EntityId::new();

        // Create facts at different times
        db.put_fact(&create_test_fact(entity1, Attribute::TestStatus, 1, 20))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestDuration, 100, 10))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestError, 3, 5))?;

        // Query facts from last 12 minutes
        let start = Utc::now() - chrono::Duration::minutes(12);
        let end = Utc::now();
        let query = Query::new().valid_time_range(TimeRange::between(start, end));
        let result = query.execute(&db)?;

        // Should get facts from 10 and 5 minutes ago, but not 20 minutes ago
        assert_eq!(result.total, 2);

        Ok(())
    }

    #[test]
    fn test_query_with_timeshift() -> Result<()> {
        let (_dir, db) = create_test_db()?;
        let entity1 = EntityId::new();

        // Create facts with both valid_time and tx_time in the past
        // Fact 1: valid 20 min ago, learned 20 min ago
        db.put_fact(&create_test_fact_with_tx_time(
            entity1,
            Attribute::TestStatus,
            1,
            20,
            20,
        ))?;
        // Fact 2: valid 10 min ago, learned 10 min ago
        db.put_fact(&create_test_fact_with_tx_time(
            entity1,
            Attribute::TestDuration,
            100,
            10,
            10,
        ))?;
        // Fact 3: valid 5 min ago, learned 5 min ago
        db.put_fact(&create_test_fact_with_tx_time(
            entity1,
            Attribute::TestError,
            3,
            5,
            5,
        ))?;

        // Query facts as they were 12 minutes ago
        // At that point, we should only know about fact 1 (20 min ago)
        let timeshift_point = Utc::now() - chrono::Duration::minutes(12);
        let query = Query::new().timeshift(TimeshiftQuery::at(timeshift_point));
        let result = query.execute(&db)?;

        // Should only see the oldest fact (from 20 minutes ago)
        assert_eq!(result.total, 1);

        Ok(())
    }

    #[test]
    fn test_query_combined_filters() -> Result<()> {
        let (_dir, db) = create_test_db()?;
        let entity1 = EntityId::new();
        let entity2 = EntityId::new();

        // Insert various facts
        db.put_fact(&create_test_fact(entity1, Attribute::TestStatus, 1, 20))?;
        db.put_fact(&create_test_fact(entity1, Attribute::TestDuration, 100, 10))?;
        db.put_fact(&create_test_fact(entity2, Attribute::TestStatus, 2, 8))?;
        db.put_fact(&create_test_fact(entity2, Attribute::TestError, 3, 5))?;

        // Query: entity1 only, last 15 minutes, limit 1
        let start = Utc::now() - chrono::Duration::minutes(15);
        let query = Query::new()
            .for_entities(vec![entity1])
            .valid_time_range(TimeRange::from(start))
            .limit(1);
        let result = query.execute(&db)?;

        assert_eq!(result.total, 1);
        assert_eq!(result.facts[0].entity_id, entity1);

        Ok(())
    }
}
