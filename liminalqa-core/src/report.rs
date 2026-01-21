//! Report data structures for Reflection

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionReport {
    pub run_id: String,
    pub plan_name: String,
    pub started_at: DateTime<Utc>,
    pub ended_at: Option<DateTime<Utc>>,
    pub summary: TestSummary,
    pub timeline: Vec<TimelineBucket>,
    pub top_slow_tests: Vec<SlowTest>,
    pub causality_trails: Vec<CausalityTrail>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestSummary {
    pub total: i64,
    pub passed: i64,
    pub failed: i64,
    pub flake: i64,
    pub timeout: i64,
    pub skip: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimelineBucket {
    pub bucket: DateTime<Utc>,
    pub status: String,
    pub count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlowTest {
    pub name: String,
    pub suite: String,
    pub duration_ms: i32,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CausalityTrail {
    pub test_name: String,
    pub test_failed_at: DateTime<Utc>,
    pub signals: Vec<NearbySignal>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NearbySignal {
    pub kind: String,
    pub at: DateTime<Utc>,
    pub value: Option<f64>,
    pub meta: serde_json::Value,
    pub time_diff_seconds: i32,
}
