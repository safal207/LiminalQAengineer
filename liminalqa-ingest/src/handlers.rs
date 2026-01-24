//! HTTP request handlers

use std::collections::HashMap;

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::*, temporal::BiTemporalTime, types::*};
use liminalqa_db::{
    query::{Query, QueryResult},
    LiminalDB,
};
use serde::{Deserialize, Serialize};
use tracing::{error, info};

use crate::{ApiResponse, AppState};

// --- DTOs ---

/// POST /ingest/run — Ingest a test run
#[derive(Debug, Serialize, Deserialize)]
pub struct RunDto {
    pub run_id: EntityId,
    pub build_id: EntityId,
    pub plan_name: String,
    pub env: serde_json::Value,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub runner_version: Option<String>,
}

/// POST /ingest/tests — Ingest multiple tests
#[derive(Debug, Serialize, Deserialize)]
pub struct TestsDto {
    pub run_id: EntityId,
    pub tests: Vec<TestDtoItem>,
    #[allow(dead_code)]
    pub valid_from: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, Serialize, Deserialize)]
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

/// POST /ingest/signals — Ingest signals
#[derive(Debug, Serialize, Deserialize)]
pub struct SignalsDto {
    pub run_id: EntityId,
    pub signals: Vec<SignalDtoItem>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SignalDtoItem {
    pub test_id: Option<EntityId>,
    pub test_name: Option<String>,
    pub kind: String,
    pub latency_ms: Option<u64>,
    pub value: Option<f64>,
    pub meta: Option<serde_json::Value>,
    pub at: chrono::DateTime<chrono::Utc>,
}

/// POST /ingest/artifacts — Ingest artifacts
#[derive(Debug, Serialize, Deserialize)]
pub struct ArtifactsDto {
    pub run_id: EntityId,
    pub artifacts: Vec<ArtifactDtoItem>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ArtifactDtoItem {
    pub test_id: Option<EntityId>,
    pub test_name: Option<String>,
    pub kind: String,
    pub path_sha256: String,
    pub path: String,
    pub size_bytes: Option<i64>,
    pub mime_type: Option<String>,
}

// --- Batch DTOs ---

#[derive(Debug, Serialize, Deserialize)]
pub struct BatchIngestDto {
    pub run: RunDto,
    #[serde(default)]
    pub tests: Vec<TestDtoItem>,
    #[serde(default)]
    pub signals: Vec<SignalDtoItem>,
    #[serde(default)]
    pub artifacts: Vec<ArtifactDtoItem>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct BatchIngestResponse {
    pub ok: bool,
    pub message: String,
    pub counts: BatchCounts,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub test_id_map: Option<HashMap<String, EntityId>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub partial_counts: Option<BatchCounts>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_details: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Default, Clone)]
pub struct BatchCounts {
    pub run: usize,
    pub tests: usize,
    pub signals: usize,
    pub artifacts: usize,
}

// --- Helper Functions ---

fn create_run_from_dto(dto: &RunDto) -> Result<Run, String> {
    let env = match serde_json::from_value::<std::collections::HashMap<String, String>>(
        dto.env.clone(),
    ) {
        Ok(env) => env,
        Err(e) => return Err(format!("Invalid env format: {}", e)),
    };

    Ok(Run {
        id: dto.run_id,
        build_id: dto.build_id,
        plan_name: dto.plan_name.clone(),
        env,
        started_at: dto.started_at,
        ended_at: None,
        runner_version: dto
            .runner_version
            .clone()
            .unwrap_or_else(|| "unknown".to_string()),
        liminal_os_version: None,
        created_at: BiTemporalTime::now(),
    })
}

fn create_test_from_dto(run_id: EntityId, item: &TestDtoItem) -> Test {
    let status = match item.status.to_lowercase().as_str() {
        "pass" | "passed" | "success" => TestStatus::Pass,
        "fail" | "failed" | "error" => TestStatus::Fail,
        "xfail" => TestStatus::XFail,
        "flake" | "flaky" => TestStatus::Flake,
        "timeout" => TestStatus::Timeout,
        _ => TestStatus::Skip,
    };

    Test {
        id: EntityId::new(),
        run_id,
        name: item.name.clone(),
        suite: item.suite.clone(),
        guidance: item.guidance.clone().unwrap_or_default(),
        status,
        duration_ms: item.duration_ms.unwrap_or(0) as u64,
        error: item
            .error
            .as_ref()
            .and_then(|e| serde_json::from_value(e.clone()).ok()),
        started_at: item.started_at.unwrap_or_else(chrono::Utc::now),
        completed_at: item.completed_at.unwrap_or_else(chrono::Utc::now),
        created_at: BiTemporalTime::now(),
    }
}

fn create_signal_from_dto(run_id: EntityId, test_id: EntityId, item: &SignalDtoItem) -> Signal {
    let signal_type = match item.kind.to_lowercase().as_str() {
        "ui" => SignalType::UI,
        "api" => SignalType::API,
        "websocket" | "ws" => SignalType::WebSocket,
        "grpc" => SignalType::GRPC,
        "database" | "db" => SignalType::Database,
        "network" => SignalType::Network,
        _ => SignalType::System,
    };

    let metadata = item
        .meta
        .as_ref()
        .and_then(|m| serde_json::from_value(m.clone()).ok())
        .unwrap_or_default();

    Signal {
        id: EntityId::new(),
        run_id,
        test_id,
        signal_type,
        timestamp: item.at,
        latency_ms: item.latency_ms,
        payload_ref: None,
        metadata,
        created_at: BiTemporalTime::now(),
    }
}

fn create_artifact_from_dto(
    run_id: EntityId,
    test_id: EntityId,
    item: &ArtifactDtoItem,
) -> Artifact {
    let artifact_type = match item.kind.to_lowercase().as_str() {
        "screenshot" => ArtifactType::Screenshot,
        "apiresponse" => ArtifactType::ApiResponse,
        "wsmessage" => ArtifactType::WsMessage,
        "grpctrace" => ArtifactType::GrpcTrace,
        "log" => ArtifactType::Log,
        "video" => ArtifactType::Video,
        _ => ArtifactType::Trace,
    };

    Artifact {
        id: EntityId::new(),
        run_id,
        test_id,
        artifact_ref: ArtifactRef {
            sha256: item.path_sha256.clone(),
            path: item.path.clone(),
            size_bytes: item
                .size_bytes
                .filter(|&v| v >= 0)
                .map(|v| v as u64)
                .unwrap_or(0),
            mime_type: item.mime_type.clone(),
        },
        artifact_type,
        description: None,
        created_at: BiTemporalTime::now(),
    }
}

fn resolve_test_id(
    db: &LiminalDB,
    test_id_map: &HashMap<String, EntityId>,
    run_id: EntityId,
    test_id: Option<EntityId>,
    test_name: Option<&str>,
    current_counts: &BatchCounts,
) -> Result<EntityId, Box<(StatusCode, Json<BatchIngestResponse>)>> {
    match test_id {
        Some(id) => Ok(id),
        None => {
            let name = test_name.ok_or_else(|| {
                Box::new((
                    StatusCode::BAD_REQUEST,
                    Json(BatchIngestResponse {
                        ok: false,
                        message: "Either test_id or test_name must be provided".to_string(),
                        counts: BatchCounts::default(),
                        test_id_map: None,
                        partial_counts: Some(current_counts.clone()),
                        error_details: None,
                    }),
                ))
            })?;

            // First check in-memory map (from tests in this batch)
            if let Some(&id) = test_id_map.get(name) {
                return Ok(id);
            }

            // Fallback to DB lookup (for tests ingested earlier)
            match db.find_test_by_name(run_id, name) {
                Ok(Some(id)) => Ok(id),
                Ok(None) => Err(Box::new((
                    StatusCode::NOT_FOUND,
                    Json(BatchIngestResponse {
                        ok: false,
                        message: format!("Test '{}' not found", name),
                        counts: BatchCounts::default(),
                        test_id_map: None,
                        partial_counts: Some(current_counts.clone()),
                        error_details: Some(format!(
                            "Test '{}' not found in batch or database",
                            name
                        )),
                    }),
                ))),
                Err(e) => Err(Box::new((
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(BatchIngestResponse {
                        ok: false,
                        message: "Database error".to_string(),
                        counts: BatchCounts::default(),
                        test_id_map: None,
                        partial_counts: Some(current_counts.clone()),
                        error_details: Some(format!("DB lookup failed: {}", e)),
                    }),
                ))),
            }
        }
    }
}

// --- Handlers ---

pub async fn ingest_run(
    State(state): State<AppState>,
    Json(dto): Json<RunDto>,
) -> impl IntoResponse {
    info!("Ingesting run: id={}", dto.run_id);

    match create_run_from_dto(&dto) {
        Ok(run) => match state.db.put_run(&run) {
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
        },
        Err(e) => (StatusCode::BAD_REQUEST, Json(ApiResponse::error(e))),
    }
}

pub async fn ingest_tests(
    State(state): State<AppState>,
    Json(dto): Json<TestsDto>,
) -> impl IntoResponse {
    info!("Ingesting {} tests", dto.tests.len());

    for item in &dto.tests {
        let test = create_test_from_dto(dto.run_id, item);

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
                            Json(ApiResponse::error(
                                "Either test_id or test_name must be provided",
                            )),
                        );
                    }
                };

                match state.db.find_test_by_name(dto.run_id, test_name) {
                    Ok(Some(id)) => {
                        info!("Resolved test_id {} for test '{}'", id, test_name);
                        id
                    }
                    Ok(None) => {
                        error!("Test '{}' not found in run {}", test_name, dto.run_id);
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
                                "Database error during test lookup: {}",
                                e
                            ))),
                        );
                    }
                }
            }
        };

        let signal = create_signal_from_dto(dto.run_id, test_id, item);

        if let Err(e) = state.db.put_signal(&signal) {
            error!("Failed to ingest signal: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!(
                    "Failed to ingest signal: {}",
                    e
                ))),
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
                            Json(ApiResponse::error(
                                "Either test_id or test_name must be provided",
                            )),
                        );
                    }
                };

                match state.db.find_test_by_name(dto.run_id, test_name) {
                    Ok(Some(id)) => {
                        info!("Resolved test_id {} for test '{}'", id, test_name);
                        id
                    }
                    Ok(None) => {
                        error!("Test '{}' not found in run {}", test_name, dto.run_id);
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
                                "Database error during test lookup: {}",
                                e
                            ))),
                        );
                    }
                }
            }
        };

        let artifact = create_artifact_from_dto(dto.run_id, test_id, item);

        if let Err(e) = state.db.put_artifact(&artifact) {
            error!("Failed to ingest artifact: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!(
                    "Failed to ingest artifact: {}",
                    e
                ))),
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

pub async fn ingest_batch(
    State(state): State<AppState>,
    Json(batch): Json<BatchIngestDto>,
) -> impl IntoResponse {
    info!(
        "Ingesting batch: run={}, tests={}, signals={}, artifacts={}",
        batch.run.run_id,
        batch.tests.len(),
        batch.signals.len(),
        batch.artifacts.len()
    );

    let mut counts = BatchCounts::default();
    let mut test_id_map: HashMap<String, EntityId> = HashMap::new();

    // Step 1: Ingest run
    let run = match create_run_from_dto(&batch.run) {
        Ok(r) => r,
        Err(e) => {
            error!("Failed to ingest run: {}", e);
            return (
                StatusCode::BAD_REQUEST,
                Json(BatchIngestResponse {
                    ok: false,
                    message: "Batch ingestion failed".to_string(),
                    counts: counts.clone(),
                    test_id_map: None,
                    partial_counts: Some(counts),
                    error_details: Some(format!("Invalid run data: {}", e)),
                }),
            );
        }
    };

    if let Err(e) = state.db.put_run(&run) {
        error!("Failed to ingest run: {}", e);
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(BatchIngestResponse {
                ok: false,
                message: "Batch ingestion failed".to_string(),
                counts: counts.clone(),
                test_id_map: None,
                partial_counts: Some(counts),
                error_details: Some(format!("Run ingestion failed: {}", e)),
            }),
        );
    }
    counts.run = 1;

    // Step 2: Ingest tests and build name -> id map
    for test_item in &batch.tests {
        let test = create_test_from_dto(batch.run.run_id, test_item);

        // Store test_name -> test_id mapping for later use
        test_id_map.insert(test.name.clone(), test.id);

        if let Err(e) = state.db.put_test(&test) {
            error!("Failed to ingest test '{}': {}", test.name, e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(BatchIngestResponse {
                    ok: false,
                    message: "Batch ingestion failed".to_string(),
                    counts: BatchCounts::default(),
                    test_id_map: None,
                    partial_counts: Some(counts),
                    error_details: Some(format!("Test ingestion failed: {}", e)),
                }),
            );
        }
        counts.tests += 1;
    }

    // Step 3: Ingest signals (using test_id_map for resolution)
    for signal_item in &batch.signals {
        let test_id = match resolve_test_id(
            &state.db,
            &test_id_map,
            batch.run.run_id,
            signal_item.test_id,
            signal_item.test_name.as_deref(),
            &counts,
        ) {
            Ok(id) => id,
            Err(boxed_resp) => return *boxed_resp,
        };

        let signal = create_signal_from_dto(batch.run.run_id, test_id, signal_item);

        if let Err(e) = state.db.put_signal(&signal) {
            error!("Failed to ingest signal: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(BatchIngestResponse {
                    ok: false,
                    message: "Batch ingestion failed".to_string(),
                    counts: BatchCounts::default(),
                    test_id_map: None,
                    partial_counts: Some(counts),
                    error_details: Some(format!("Signal ingestion failed: {}", e)),
                }),
            );
        }
        counts.signals += 1;
    }

    // Step 4: Ingest artifacts (using test_id_map for resolution)
    for artifact_item in &batch.artifacts {
        let test_id = match resolve_test_id(
            &state.db,
            &test_id_map,
            batch.run.run_id,
            artifact_item.test_id,
            artifact_item.test_name.as_deref(),
            &counts,
        ) {
            Ok(id) => id,
            Err(boxed_resp) => return *boxed_resp,
        };

        let artifact = create_artifact_from_dto(batch.run.run_id, test_id, artifact_item);

        if let Err(e) = state.db.put_artifact(&artifact) {
            error!("Failed to ingest artifact: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(BatchIngestResponse {
                    ok: false,
                    message: "Batch ingestion failed".to_string(),
                    counts: BatchCounts::default(),
                    test_id_map: None,
                    partial_counts: Some(counts),
                    error_details: Some(format!("Artifact ingestion failed: {}", e)),
                }),
            );
        }
        counts.artifacts += 1;
    }

    // Step 5: Flush to disk
    if let Err(e) = state.db.flush() {
        error!("Failed to flush db: {}", e);
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(BatchIngestResponse {
                ok: false,
                message: "Batch ingestion failed during flush".to_string(),
                counts: BatchCounts::default(),
                test_id_map: None,
                partial_counts: Some(counts),
                error_details: Some(format!("Flush failed: {}", e)),
            }),
        );
    }

    info!("Batch ingestion successful: {:?}", counts);

    (
        StatusCode::OK,
        Json(BatchIngestResponse {
            ok: true,
            message: "Batch ingestion successful".to_string(),
            counts,
            test_id_map: Some(test_id_map),
            partial_counts: None,
            error_details: None,
        }),
    )
}

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
