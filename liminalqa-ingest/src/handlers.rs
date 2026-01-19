//! HTTP request handlers

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::*, temporal::BiTemporalTime, types::*};
use liminalqa_db::query::{Query, QueryResult};
use serde::Deserialize;
use tracing::{error, info};

use crate::{ApiResponse, AppState};

/// POST /ingest/run — Ingest a test run
#[derive(Debug, Deserialize)]
pub struct RunDto {
    pub run_id: EntityId,
    pub build_id: EntityId,
    pub plan_name: String,
    pub env: serde_json::Value,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub runner_version: Option<String>,
}

pub async fn ingest_run(
    State(state): State<AppState>,
    Json(dto): Json<RunDto>,
) -> impl IntoResponse {
    info!("Ingesting run: id={}", dto.run_id);

    let env = match serde_json::from_value::<std::collections::HashMap<String, String>>(dto.env.clone()) {
        Ok(env) => env,
        Err(e) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(ApiResponse::error(format!("Invalid env format: {}", e))),
            );
        }
    };

    let run = Run {
        id: dto.run_id,
        build_id: dto.build_id,
        plan_name: dto.plan_name,
        env,
        started_at: dto.started_at,
        ended_at: None,
        runner_version: dto.runner_version.unwrap_or_else(|| "unknown".to_string()),
        liminal_os_version: None,
        created_at: BiTemporalTime::now(),
    };

    match state.db.put_run(&run) {
        Ok(_) => {
            if let Err(e) = state.db.flush() {
                error!("Failed to flush db: {}", e);
            }
            (
                StatusCode::OK,
                Json(ApiResponse::ok("Run ingested successfully")),
            )
        }
        Err(e) => {
            error!("Failed to ingest run: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest run: {}", e))),
            )
        }
    }
}

/// POST /ingest/tests — Ingest multiple tests
#[derive(Debug, Deserialize)]
pub struct TestsDto {
    pub run_id: EntityId,
    pub tests: Vec<TestDtoItem>,
    pub valid_from: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, Deserialize)]
pub struct TestDtoItem {
    pub name: String,
    pub suite: String,
    pub guidance: Option<String>,
    pub status: String,
    pub duration_ms: Option<i32>,
    pub error: Option<serde_json::Value>,
    pub started_at: Option<chrono::DateTime<chrono::Utc>>,
    pub completed_at: Option<chrono::DateTime<chrono::Utc>>,
}

pub async fn ingest_tests(
    State(state): State<AppState>,
    Json(dto): Json<TestsDto>,
) -> impl IntoResponse {
    info!("Ingesting {} tests", dto.tests.len());

    for item in &dto.tests {
        let status = match item.status.to_lowercase().as_str() {
            "pass" | "passed" | "success" => TestStatus::Pass,
            "fail" | "failed" | "error" => TestStatus::Fail,
            "xfail" => TestStatus::XFail,
            "flake" | "flaky" => TestStatus::Flake,
            "timeout" => TestStatus::Timeout,
            _ => TestStatus::Skip,
        };

        let test = Test {
            id: EntityId::new(),
            run_id: dto.run_id,
            name: item.name.clone(),
            suite: item.suite.clone(),
            guidance: item.guidance.clone().unwrap_or_default(),
            status,
            duration_ms: item.duration_ms.unwrap_or(0) as u64,
            error: item.error.as_ref().and_then(|e| serde_json::from_value(e.clone()).ok()),
            started_at: item.started_at.unwrap_or_else(chrono::Utc::now),
            completed_at: item.completed_at.unwrap_or_else(chrono::Utc::now),
            created_at: BiTemporalTime::now(),
        };

        if let Err(e) = state.db.put_test(&test) {
            error!("Failed to ingest test: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest test: {}", e))),
            );
        }
    }

    if let Err(e) = state.db.flush() {
        error!("Failed to flush db: {}", e);
    }

    (
        StatusCode::OK,
        Json(ApiResponse::ok(format!(
            "{} tests ingested successfully",
            dto.tests.len()
        ))),
    )
}

/// POST /ingest/signals — Ingest signals
#[derive(Debug, Deserialize)]
pub struct SignalsDto {
    pub run_id: EntityId,
    pub signals: Vec<SignalDtoItem>,
}

#[derive(Debug, Deserialize)]
pub struct SignalDtoItem {
    pub test_id: Option<EntityId>,
    pub test_name: Option<String>,
    pub kind: String,
    pub latency_ms: Option<u64>,
    pub value: Option<f64>,
    pub meta: Option<serde_json::Value>,
    pub at: chrono::DateTime<chrono::Utc>,
}

pub async fn ingest_signals(
    State(state): State<AppState>,
    Json(dto): Json<SignalsDto>,
) -> impl IntoResponse {
    // Validate that all signals have either test_id or valid test_name
    for item in &dto.signals {
        if item.test_id.is_none() && item.test_name.is_none() {
            return (
                StatusCode::BAD_REQUEST,
                Json(ApiResponse::error(
                    "Each signal must have either test_id or test_name",
                )),
            );
        }
    }

    info!("Ingesting {} signals", dto.signals.len());

    for item in &dto.signals {
        let signal_type = match item.kind.to_lowercase().as_str() {
            "ui" => SignalType::UI,
            "api" => SignalType::API,
            "websocket" | "ws" => SignalType::WebSocket,
            "grpc" => SignalType::GRPC,
            "database" | "db" => SignalType::Database,
            "network" => SignalType::Network,
            _ => SignalType::System,
        };

        let metadata = item.meta.as_ref()
            .and_then(|m| serde_json::from_value(m.clone()).ok())
            .unwrap_or_default();

        // Resolve test_id from test_name if needed
        let test_id = match item.test_id {
            Some(id) => id,
            None => {
                let test_name = match item.test_name.as_ref() {
                    Some(name) => name,
                    None => {
                        error!("Neither test_id nor test_name provided for signal");
                        return (
                            StatusCode::BAD_REQUEST,
                            Json(ApiResponse::error("Either test_id or test_name must be provided")),
                        );
                    }
                };

                match state.db.find_test_by_name(dto.run_id, test_name) {
                    Ok(Some(id)) => {
                        info!("Resolved test_id {} for test '{}'", id, test_name);
                        id
                    }
                    Ok(None) => {
                        error!(
                            "Test '{}' not found in run {}",
                            test_name, dto.run_id
                        );
                        return (
                            StatusCode::NOT_FOUND,
                            Json(ApiResponse::error(format!(
                                "Test '{}' not found in run {}. Ensure tests are ingested via POST /ingest/tests before sending signals.",
                                test_name, dto.run_id
                            ))),
                        );
                    }
                    Err(e) => {
                        error!("Database error during test lookup: {}", e);
                        return (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(ApiResponse::error(format!(
                                "Database error during test lookup: {}", e
                            ))),
                        );
                    }
                }
            }
        };

        let signal = Signal {
            id: EntityId::new(),
            run_id: dto.run_id,
            test_id,
            signal_type,
            timestamp: item.at,
            latency_ms: item.latency_ms,
            payload_ref: None,
            metadata,
            created_at: BiTemporalTime::now(),
        };

        if let Err(e) = state.db.put_signal(&signal) {
            error!("Failed to ingest signal: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest signal: {}", e))),
            );
        }
    }

    if let Err(e) = state.db.flush() {
        error!("Failed to flush db: {}", e);
    }

    (
        StatusCode::OK,
        Json(ApiResponse::ok(format!(
            "{} signals ingested successfully",
            dto.signals.len()
        ))),
    )
}

/// POST /ingest/artifacts — Ingest artifacts
#[derive(Debug, Deserialize)]
pub struct ArtifactsDto {
    pub run_id: EntityId,
    pub artifacts: Vec<ArtifactDtoItem>,
}

#[derive(Debug, Deserialize)]
pub struct ArtifactDtoItem {
    pub test_id: Option<EntityId>,
    pub test_name: Option<String>,
    pub kind: String,
    pub path_sha256: String,
    pub path: String,
    pub size_bytes: Option<i64>,
    pub mime_type: Option<String>,
}

pub async fn ingest_artifacts(
    State(state): State<AppState>,
    Json(dto): Json<ArtifactsDto>,
) -> impl IntoResponse {
    // Validate that all artifacts have either test_id or valid test_name
    for item in &dto.artifacts {
        if item.test_id.is_none() && item.test_name.is_none() {
            return (
                StatusCode::BAD_REQUEST,
                Json(ApiResponse::error(
                    "Each artifact must have either test_id or test_name",
                )),
            );
        }
    }

    info!("Ingesting {} artifacts", dto.artifacts.len());

    for item in &dto.artifacts {
        let artifact_type = match item.kind.to_lowercase().as_str() {
            "screenshot" => ArtifactType::Screenshot,
            "apiresponse" => ArtifactType::ApiResponse,
            "wsmessage" => ArtifactType::WsMessage,
            "grpctrace" => ArtifactType::GrpcTrace,
            "log" => ArtifactType::Log,
            "video" => ArtifactType::Video,
            _ => ArtifactType::Trace,
        };

        // Resolve test_id from test_name if needed
        let test_id = match item.test_id {
            Some(id) => id,
            None => {
                let test_name = match item.test_name.as_ref() {
                    Some(name) => name,
                    None => {
                        error!("Neither test_id nor test_name provided for artifact");
                        return (
                            StatusCode::BAD_REQUEST,
                            Json(ApiResponse::error("Either test_id or test_name must be provided")),
                        );
                    }
                };

                match state.db.find_test_by_name(dto.run_id, test_name) {
                    Ok(Some(id)) => {
                        info!("Resolved test_id {} for test '{}'", id, test_name);
                        id
                    }
                    Ok(None) => {
                        error!(
                            "Test '{}' not found in run {}",
                            test_name, dto.run_id
                        );
                        return (
                            StatusCode::NOT_FOUND,
                            Json(ApiResponse::error(format!(
                                "Test '{}' not found in run {}. Ensure tests are ingested via POST /ingest/tests before sending artifacts.",
                                test_name, dto.run_id
                            ))),
                        );
                    }
                    Err(e) => {
                        error!("Database error during test lookup: {}", e);
                        return (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(ApiResponse::error(format!(
                                "Database error during test lookup: {}", e
                            ))),
                        );
                    }
                }
            }
        };

        let artifact = Artifact {
            id: EntityId::new(),
            run_id: dto.run_id,
            test_id,
            artifact_ref: ArtifactRef {
                sha256: item.path_sha256.clone(),
                path: item.path.clone(),
                size_bytes: item.size_bytes.filter(|&v| v >= 0).map(|v| v as u64).unwrap_or(0),
                mime_type: item.mime_type.clone(),
            },
            artifact_type,
            description: None,
            created_at: BiTemporalTime::now(),
        };

        if let Err(e) = state.db.put_artifact(&artifact) {
            error!("Failed to ingest artifact: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest artifact: {}", e))),
            );
        }
    }

    if let Err(e) = state.db.flush() {
        error!("Failed to flush db: {}", e);
    }

    (
        StatusCode::OK,
        Json(ApiResponse::ok(format!(
            "{} artifacts ingested successfully",
            dto.artifacts.len()
        ))),
    )
}

/// POST /query — Execute a query
pub async fn query_handler(
    State(_state): State<AppState>,
    Json(query): Json<Query>,
) -> impl IntoResponse {
    info!("Executing query: {:?}", query);

    // TODO: Implement query execution
    // For now, return empty result
    let result = QueryResult::new(vec![]);

    (StatusCode::OK, Json(result))
}
