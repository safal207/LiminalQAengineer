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
    XFail,  // Expected failure
    Flake,  // Inconsistent
    Timeout,
    Skip,
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
    pub score: f64,  // 0.0 to 1.0
    pub occurrences: u32,
    pub first_seen: chrono::DateTime<chrono::Utc>,
    pub last_seen: chrono::DateTime<chrono::Utc>,
}
