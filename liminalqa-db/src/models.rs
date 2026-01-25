use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct TestRun {
    pub id: String,
    pub build_id: Option<String>,
    pub plan_name: String,
    pub status: String,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<i32>,
    pub environment: serde_json::Value,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct TestResult {
    pub id: String,
    pub run_id: String,
    pub name: String,
    pub suite: String,
    pub status: String,
    pub duration_ms: i32,
    pub error_message: Option<String>,
    pub stack_trace: Option<String>,
    pub metadata: serde_json::Value,
    pub executed_at: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Baseline {
    pub test_name: String,
    pub suite: String,
    pub mean_duration_ms: f64,
    pub stddev_duration_ms: f64,
    pub sample_size: i32,
    pub last_updated: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct DriftDataPoint {
    pub timestamp: DateTime<Utc>,
    pub duration_ms: i32,
    pub mean_duration_ms: Option<f64>,
    pub stddev_duration_ms: Option<f64>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct ResonanceScore {
    pub test_name: String,
    pub suite: String,
    pub score: f64,
    pub correlated_tests: Option<Vec<String>>,
    pub last_calculated: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct SignalEntity {
    pub id: String,
    pub test_id: String,
    pub signal_type: String,
    pub timestamp: DateTime<Utc>,
    pub value: serde_json::Value,
    pub metadata: Option<serde_json::Value>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct ArtifactEntity {
    pub id: String,
    pub test_id: String,
    pub artifact_type: String,
    pub file_path: String,
    pub content_hash: Option<String>,
    pub size_bytes: Option<i64>,
    pub metadata: Option<serde_json::Value>,
    pub created_at: DateTime<Utc>,
}
