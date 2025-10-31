//! Query interface for bi-temporal data

use anyhow::Result;
use liminalqa_core::{
    temporal::{TimeRange, TimeshiftQuery},
    types::EntityId,
};
use serde::{Deserialize, Serialize};

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
