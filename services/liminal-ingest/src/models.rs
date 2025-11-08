//! Data models for ingest API

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Deserialize, Serialize)]
pub struct ApiResponse {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

impl ApiResponse {
    pub fn ok() -> Self {
        Self { ok: true, error: None }
    }

    pub fn error(msg: impl Into<String>) -> Self {
        Self {
            ok: false,
            error: Some(msg.into()),
        }
    }
}

// Run envelope
#[derive(Debug, Deserialize)]
pub struct RunDto {
    pub run_id: Uuid,
    pub build_id: Option<Uuid>,
    pub plan_name: String,
    pub env: serde_json::Value,
    pub started_at: DateTime<Utc>,
    pub runner_version: Option<String>,
}

// Tests envelope
#[derive(Debug, Deserialize)]
pub struct TestsDto {
    pub run_id: Uuid,
    pub tests: Vec<TestDto>,
    #[serde(default = "Utc::now")]
    pub valid_from: DateTime<Utc>,
}

#[derive(Debug, Deserialize)]
pub struct TestDto {
    pub name: String,
    pub suite: String,
    pub guidance: Option<String>,
    pub status: String, // "pass", "fail", "xfail", "flake", "timeout", "skip"
    pub duration_ms: Option<i32>,
    pub error: Option<serde_json::Value>,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
}

// Signals envelope
#[derive(Debug, Deserialize)]
pub struct SignalsDto {
    pub run_id: Uuid,
    pub signals: Vec<SignalDto>,
}

#[derive(Debug, Deserialize)]
pub struct SignalDto {
    pub test_name: Option<String>,
    pub kind: String, // "ui", "api", "websocket", "grpc", "database", "network", "system"
    pub latency_ms: Option<i32>,
    pub value: Option<f64>,
    pub meta: Option<serde_json::Value>,
    pub at: DateTime<Utc>,
}

// Artifacts envelope
#[derive(Debug, Deserialize)]
pub struct ArtifactsDto {
    pub run_id: Uuid,
    pub artifacts: Vec<ArtifactDto>,
}

#[derive(Debug, Deserialize)]
pub struct ArtifactDto {
    pub test_name: Option<String>,
    pub kind: String, // "screenshot", "api_response", "ws_message", "grpc_trace", "log", "video", "trace"
    pub path_sha256: String,
    pub path: String,
    pub size_bytes: Option<i64>,
    pub mime_type: Option<String>,
}
