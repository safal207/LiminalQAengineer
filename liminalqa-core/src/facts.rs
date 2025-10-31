//! Fact representation for bi-temporal storage

use crate::{temporal::BiTemporalTime, types::EntityId};
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// A fact is an attribute-value pair attached to an entity at a specific point in bi-temporal time
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fact {
    pub entity_id: EntityId,
    pub attribute: Attribute,
    pub value: Value,
    pub time: BiTemporalTime,
}

impl Fact {
    pub fn new(entity_id: EntityId, attribute: Attribute, value: Value) -> Self {
        Self {
            entity_id,
            attribute,
            value,
            time: BiTemporalTime::now(),
        }
    }

    pub fn with_time(
        entity_id: EntityId,
        attribute: Attribute,
        value: Value,
        time: BiTemporalTime,
    ) -> Self {
        Self {
            entity_id,
            attribute,
            value,
            time,
        }
    }
}

/// Predefined attributes (extensible via custom namespace)
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Attribute {
    // Test attributes
    #[serde(rename = ":test/status")]
    TestStatus,
    #[serde(rename = ":test/duration")]
    TestDuration,
    #[serde(rename = ":test/error")]
    TestError,
    #[serde(rename = ":test/guidance")]
    TestGuidance,

    // UI attributes
    #[serde(rename = ":ui/screenshot")]
    UiScreenshot,
    #[serde(rename = ":ui/interaction")]
    UiInteraction,

    // API attributes
    #[serde(rename = ":api/response")]
    ApiResponse,
    #[serde(rename = ":api/status_code")]
    ApiStatusCode,
    #[serde(rename = ":api/latency")]
    ApiLatency,

    // WebSocket attributes
    #[serde(rename = ":ws/message")]
    WsMessage,
    #[serde(rename = ":ws/latency")]
    WsLatency,
    #[serde(rename = ":ws/connection_state")]
    WsConnectionState,

    // gRPC attributes
    #[serde(rename = ":grpc/method")]
    GrpcMethod,
    #[serde(rename = ":grpc/status")]
    GrpcStatus,
    #[serde(rename = ":grpc/latency")]
    GrpcLatency,

    // Run attributes
    #[serde(rename = ":run/env")]
    RunEnv,
    #[serde(rename = ":run/started_at")]
    RunStartedAt,
    #[serde(rename = ":run/ended_at")]
    RunEndedAt,
    #[serde(rename = ":run/status")]
    RunStatus,

    // Resonance attributes
    #[serde(rename = ":resonance/pattern")]
    ResonancePattern,
    #[serde(rename = ":resonance/score")]
    ResonanceScore,

    // Custom attribute
    Custom(String),
}

impl std::fmt::Display for Attribute {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Custom(s) => write!(f, "{}", s),
            _ => {
                let json = serde_json::to_string(self).unwrap_or_default();
                write!(f, "{}", json.trim_matches('"'))
            }
        }
    }
}

/// Batch of facts for efficient ingestion
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FactBatch {
    pub facts: Vec<Fact>,
    pub batch_id: EntityId,
    pub ingested_at: chrono::DateTime<chrono::Utc>,
}

impl FactBatch {
    pub fn new(facts: Vec<Fact>) -> Self {
        Self {
            facts,
            batch_id: crate::types::new_entity_id(),
            ingested_at: chrono::Utc::now(),
        }
    }
}
