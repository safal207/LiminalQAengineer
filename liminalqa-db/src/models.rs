// liminalqa-db/src/models.rs

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

// ============================================================================
// CORE TYPES (Phase 4)
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct TestRun {
    pub id: String,
    pub build_id: Option<String>,
    pub plan_name: String,
    pub status: String,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<i32>,
    pub environment: Option<serde_json::Value>,
    pub metadata: Option<serde_json::Value>,
    pub created_at: DateTime<Utc>,

    // Access Protocol fields (Phase 5 - reserved)
    pub protocol_version: Option<String>,
    pub self_resonance_score: Option<f64>,
    pub world_resonance_score: Option<f64>,
    pub overall_alignment_score: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct TestResult {
    pub id: String,
    pub run_id: String,
    pub name: String,
    pub suite: String,
    pub status: String,
    pub duration_ms: i32,
    pub error_message: Option<String>,
    pub stack_trace: Option<String>,
    pub metadata: Option<serde_json::Value>,
    pub executed_at: DateTime<Utc>,
    pub created_at: DateTime<Utc>,

    // Access Protocol fields (Phase 5 - optional for now)
    #[serde(skip_serializing_if = "Option::is_none")]
    #[sqlx(skip)]
    pub protocol_metrics: Option<ProtocolMetrics>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolMetrics {
    // Self Resonance (Phase 0)
    pub self_resonance_score: Option<f64>,
    pub intent_clarity: Option<String>,
    pub resonance_frequency: Option<String>,
    pub readiness_state: Option<String>,

    // Assembly (Phase 2)
    pub resonating_elements: Option<serde_json::Value>,
    pub filtered_noise: Option<serde_json::Value>,

    // Orientation (Phase 3)
    pub axis_centered: Option<bool>,
    pub internal_direction: Option<String>,

    // Transition (Phase 4)
    pub transition_smoothness: Option<f64>,
    pub resonance_preserved: Option<bool>,

    // Movement (Phase 5)
    pub step_from_center: Option<bool>,
    pub energy_efficiency: Option<f64>,
    pub energy_waste: Option<f64>,

    // Trajectory (Phase 6)
    pub trajectory_reality: Option<bool>,
    pub alignment_status: Option<String>,
    pub path_pattern: Option<serde_json::Value>,

    // World Resonance (Phase 7)
    pub world_resonance_score: Option<f64>,
    pub mutual_influence: Option<bool>,
    pub feedback_count: Option<i32>,
    pub learning_count: Option<i32>,
    pub learnings: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Baseline {
    pub id: i32,
    pub test_name: String,
    pub suite: String,
    pub mean_duration_ms: f64,
    pub stddev_duration_ms: f64,
    pub sample_size: i32,
    pub last_updated: DateTime<Utc>,
    pub created_at: DateTime<Utc>,

    // Access Protocol baselines (Phase 5)
    pub mean_self_resonance: Option<f64>,
    pub mean_energy_efficiency: Option<f64>,
    pub mean_world_resonance: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct ResonanceScore {
    pub id: i32,
    pub test_name: String,
    pub suite: String,
    pub score: f64,
    pub correlated_tests: Vec<String>,
    pub last_calculated: DateTime<Utc>,
    pub created_at: DateTime<Utc>,

    // Access Protocol correlation (Phase 5)
    pub correlation_type: Option<String>,
    pub correlation_strength: Option<f64>,
    pub pattern_description: Option<String>,
}

// ============================================================================
// QUERY RESULT TYPES
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftDataPoint {
    pub timestamp: DateTime<Utc>,
    pub duration_ms: i32,
    pub mean_duration_ms: f64,
    pub stddev_duration_ms: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct ProtocolQualityView {
    pub id: String,
    pub name: String,
    pub suite: String,
    pub status: String,
    pub duration_ms: i32,
    pub self_resonance_score: Option<f64>,
    pub energy_efficiency: Option<f64>,
    pub trajectory_reality: Option<bool>,
    pub world_resonance_score: Option<f64>,
    pub mutual_influence: Option<bool>,
    pub learning_count: Option<i32>,
    pub overall_protocol_quality: Option<f64>,
}
