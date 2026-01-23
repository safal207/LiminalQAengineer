//! Bi-temporal time model

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Bi-temporal timestamp: valid_time (truth) × tx_time (knowledge)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct BiTemporalTime {
    /// When this fact was true in the real world
    pub valid_time: DateTime<Utc>,
    /// When we learned about this fact (transaction time)
    pub tx_time: DateTime<Utc>,
}

impl BiTemporalTime {
    pub fn now() -> Self {
        let now = Utc::now();
        Self {
            valid_time: now,
            tx_time: now,
        }
    }

    pub fn with_valid_time(valid_time: DateTime<Utc>) -> Self {
        Self {
            valid_time,
            tx_time: Utc::now(),
        }
    }

    pub fn with_times(valid_time: DateTime<Utc>, tx_time: DateTime<Utc>) -> Self {
        Self {
            valid_time,
            tx_time,
        }
    }
}

/// Time range for queries
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct TimeRange {
    pub start: DateTime<Utc>,
    pub end: Option<DateTime<Utc>>,
}

impl TimeRange {
    pub fn from(start: DateTime<Utc>) -> Self {
        Self { start, end: None }
    }

    pub fn between(start: DateTime<Utc>, end: DateTime<Utc>) -> Self {
        Self {
            start,
            end: Some(end),
        }
    }

    pub fn contains(&self, time: DateTime<Utc>) -> bool {
        #[allow(clippy::unnecessary_map_or)]
        if time >= self.start {
            self.end.map_or(true, |end| time <= end)
        } else {
            false
        }
    }
}

/// Timeshift query: view the world as it was at a specific moment
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct TimeshiftQuery {
    pub valid_time: DateTime<Utc>,
    pub tx_time: DateTime<Utc>,
}

impl TimeshiftQuery {
    pub fn at(time: DateTime<Utc>) -> Self {
        Self {
            valid_time: time,
            tx_time: time,
        }
    }

    pub fn valid_at_tx(valid_time: DateTime<Utc>, tx_time: DateTime<Utc>) -> Self {
        Self {
            valid_time,
            tx_time,
        }
    }
}
