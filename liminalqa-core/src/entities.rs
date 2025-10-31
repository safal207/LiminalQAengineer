//! Entity definitions for LIMINAL-DB

use crate::{temporal::BiTemporalTime, types::*};
use serde::{Deserialize, Serialize};

/// Base entity trait
pub trait Entity {
    fn id(&self) -> EntityId;
    fn entity_type(&self) -> EntityType;
}

/// Entity type enumeration
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EntityType {
    System,
    Build,
    Run,
    Test,
    Artifact,
    Signal,
    Resonance,
}

/// System under test
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct System {
    pub id: EntityId,
    pub name: String,
    pub version: String,
    pub repository: Option<String>,
    pub created_at: BiTemporalTime,
}

impl Entity for System {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::System
    }
}

/// Build artifact
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Build {
    pub id: EntityId,
    pub system_id: EntityId,
    pub commit_sha: String,
    pub branch: String,
    pub build_number: Option<u64>,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub completed_at: Option<chrono::DateTime<chrono::Utc>>,
    pub status: BuildStatus,
    pub created_at: BiTemporalTime,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum BuildStatus {
    Pending,
    Running,
    Success,
    Failed,
    Cancelled,
}

impl Entity for Build {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::Build
    }
}

/// Test run (hermetic execution)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Run {
    pub id: EntityId,
    pub build_id: EntityId,
    pub plan_name: String,
    pub env: Environment,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub ended_at: Option<chrono::DateTime<chrono::Utc>>,
    pub runner_version: String,
    pub liminal_os_version: Option<String>,
    pub created_at: BiTemporalTime,
}

impl Entity for Run {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::Run
    }
}

/// Individual test (Guidance → Co-Navigation → Council → Reflection)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Test {
    pub id: EntityId,
    pub run_id: EntityId,
    pub name: String,
    pub suite: String,
    pub guidance: String,  // Test intention
    pub status: TestStatus,
    pub duration_ms: u64,
    pub error: Option<TestError>,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub completed_at: chrono::DateTime<chrono::Utc>,
    pub created_at: BiTemporalTime,
}

impl Entity for Test {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::Test
    }
}

/// Artifact (screenshot, API response, etc.)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Artifact {
    pub id: EntityId,
    pub test_id: EntityId,
    pub artifact_ref: ArtifactRef,
    pub artifact_type: ArtifactType,
    pub description: Option<String>,
    pub created_at: BiTemporalTime,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ArtifactType {
    Screenshot,
    ApiResponse,
    WsMessage,
    GrpcTrace,
    Log,
    Video,
    Trace,
}

impl Entity for Artifact {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::Artifact
    }
}

/// Signal (UI/API/WS/gRPC observation)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Signal {
    pub id: EntityId,
    pub test_id: EntityId,
    pub signal_type: SignalType,
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub latency_ms: Option<u64>,
    pub payload_ref: Option<ArtifactRef>,
    pub metadata: std::collections::HashMap<String, serde_json::Value>,
    pub created_at: BiTemporalTime,
}

impl Entity for Signal {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::Signal
    }
}

/// Resonance (pattern of instability)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Resonance {
    pub id: EntityId,
    pub pattern: ResonancePattern,
    pub affected_tests: Vec<EntityId>,
    pub root_cause: Option<String>,
    pub created_at: BiTemporalTime,
}

impl Entity for Resonance {
    fn id(&self) -> EntityId {
        self.id
    }
    fn entity_type(&self) -> EntityType {
        EntityType::Resonance
    }
}
