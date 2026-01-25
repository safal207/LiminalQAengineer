//! Core type definitions

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// ULID-based unique identifier
pub type EntityId = ulid::Ulid;

/// Generate a new entity ID
pub fn new_entity_id() -> EntityId {
    ulid::Ulid::new()
}

/// Test status enumeration
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TestStatus {
    Pass,
    Fail,
    XFail, // Expected failure
    Flake, // Inconsistent
    Timeout,
    Skip,
}

impl TestStatus {
    pub fn is_pass(&self) -> bool {
        matches!(self, Self::Pass)
    }
}

/// Run status enumeration
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RunStatus {
    Running,
    Passed,
    Failed,
    Error,
}

/// Signal type classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SignalType {
    UI,
    API,
    WebSocket,
    GRPC,
    Database,
    Network,
    System,
}

/// Error classification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestError {
    pub error_type: String,
    pub message: String,
    pub stack_trace: Option<String>,
    pub source_location: Option<SourceLocation>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceLocation {
    pub file: String,
    pub line: u32,
    pub column: Option<u32>,
}

/// Environment snapshot
pub type Environment = HashMap<String, String>;

/// Artifact reference (content-addressed)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtifactRef {
    pub sha256: String,
    pub path: String,
    pub size_bytes: u64,
    pub mime_type: Option<String>,
}

/// Resonance pattern (for flake detection)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResonancePattern {
    pub pattern_id: EntityId,
    pub description: String,
    pub score: f64, // 0.0 to 1.0
    pub occurrences: u32,
    pub first_seen: chrono::DateTime<chrono::Utc>,
    pub last_seen: chrono::DateTime<chrono::Utc>,
}

// --- Phase 5: Access Protocol Types ---

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Frequency {
    High,
    Centered,
    Low,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ReadinessState {
    Aligned,
    Checking,
    Misaligned,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum InternalDirection {
    Aligned,
    Exploring,
    Reactive,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AlignmentStatus {
    Aligned,
    Checking,
    Illusion,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtocolMetrics {
    // Self Resonance
    pub self_resonance_score: Option<f64>,
    pub intent_clarity: Option<String>,
    pub resonance_frequency: Option<Frequency>,
    pub readiness_state: Option<ReadinessState>,

    // Assembly
    pub resonating_elements: Option<serde_json::Value>,
    pub filtered_noise: Option<serde_json::Value>,

    // Orientation
    pub axis_centered: Option<bool>,
    pub internal_direction: Option<InternalDirection>,

    // Transition
    pub transition_smoothness: Option<f64>,
    pub resonance_preserved: Option<bool>,

    // Movement
    pub step_from_center: Option<bool>,
    pub energy_efficiency: Option<f64>,
    pub energy_waste: Option<f64>,

    // Trajectory
    pub trajectory_reality: Option<bool>,
    pub alignment_status: Option<AlignmentStatus>,
    pub path_pattern: Option<serde_json::Value>,

    // World Resonance
    pub world_resonance_score: Option<f64>,
    pub mutual_influence: Option<bool>,
    pub feedback_count: Option<i32>,
    pub learning_count: Option<i32>,
    pub learnings: Option<serde_json::Value>,

    // Overall Protocol Quality
    pub protocol_cycle_valid: Option<bool>,
    pub protocol_validation_errors: Option<serde_json::Value>,
}
