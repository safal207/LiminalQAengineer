//! HTTP request handlers

use std::collections::HashMap;

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::*, metrics::TestLabels, temporal::BiTemporalTime, types::*};
use liminalqa_db::{
    models::{ArtifactEntity, SignalEntity, TestResult, TestRun},
    query::{Query, QueryResult},
    PostgresStorage,
};
use serde::{Deserialize, Serialize};
use tracing::{error, info};

use crate::{
    baseline::check_baseline_drift, resonance::check_and_record_flakiness, ApiResponse, AppState,
};

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

fn create_run_from_dto(dto: &RunDto) -> Result<TestRun, String> {
    Ok(TestRun {
        id: dto.run_id.to_string(),
        build_id: Some(dto.build_id.to_string()),
        plan_name: dto.plan_name.clone(),
        status: "running".to_string(), // Default status
        started_at: dto.started_at,
        completed_at: None,
        duration_ms: None,
        environment: dto.env.clone(),
        metadata: serde_json::json!({
            "runner_version": dto.runner_version
        }),
        created_at: chrono::Utc::now(),
    })
}

fn create_test_from_dto(run_id: EntityId, item: &TestDtoItem) -> (Test, TestResult) {
    let status = match item.status.to_lowercase().as_str() {
        "pass" | "passed" | "success" => TestStatus::Pass,
        "fail" | "failed" | "error" => TestStatus::Fail,
        "xfail" => TestStatus::XFail,
        "flake" | "flaky" => TestStatus::Flake,
        "timeout" => TestStatus::Timeout,
        _ => TestStatus::Skip,
    };

    let test_id = EntityId::new();
    let started_at = item.started_at.unwrap_or_else(chrono::Utc::now);
    let completed_at = item.completed_at.unwrap_or_else(chrono::Utc::now);

    let test_entity = Test {
        id: test_id,
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
        started_at,
        completed_at,
        created_at: BiTemporalTime::now(),
    };

    let error_message = test_entity.error.as_ref().map(|e| e.message.clone());
    let stack_trace = test_entity
        .error
        .as_ref()
        .and_then(|e| e.stack_trace.clone());

    let test_result = TestResult {
        id: test_id.to_string(),
        run_id: run_id.to_string(),
        name: item.name.clone(),
        suite: item.suite.clone(),
        status: format!("{:?}", status).to_lowercase(),
        duration_ms: item.duration_ms.unwrap_or(0),
        error_message,
        stack_trace,
        metadata: serde_json::json!({
            "guidance": item.guidance
        }),
        executed_at: started_at,
        created_at: chrono::Utc::now(),
    };

    (test_entity, test_result)
}

fn create_signal_from_dto(
    _run_id: EntityId,
    test_id: EntityId,
    item: &SignalDtoItem,
) -> SignalEntity {
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

    SignalEntity {
        id: EntityId::new().to_string(),
        test_id: test_id.to_string(),
        signal_type: format!("{:?}", signal_type).to_lowercase(),
        timestamp: item.at,
        value: serde_json::json!({
            "latency_ms": item.latency_ms,
            "value": item.value
        }),
        metadata: Some(metadata),
        created_at: chrono::Utc::now(),
    }
}

fn create_artifact_from_dto(
    _run_id: EntityId,
    test_id: EntityId,
    item: &ArtifactDtoItem,
) -> ArtifactEntity {
    ArtifactEntity {
        id: EntityId::new().to_string(),
        test_id: test_id.to_string(),
        artifact_type: item.kind.clone(),
        file_path: item.path.clone(),
        content_hash: Some(item.path_sha256.clone()),
        size_bytes: item.size_bytes,
        metadata: Some(serde_json::json!({
            "mime_type": item.mime_type
        })),
        created_at: chrono::Utc::now(),
    }
}

async fn resolve_test_id(
    db: &PostgresStorage,
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

            // Fallback to DB lookup
            match db.find_test_by_name(&run_id.to_string(), name).await {
                Ok(Some(id_str)) => match EntityId::from_string(&id_str) {
                    Ok(id) => Ok(id),
                    Err(_) => Err(Box::new((
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(BatchIngestResponse {
                            ok: false,
                            message: "Invalid test ID in database".to_string(),
                            counts: BatchCounts::default(),
                            test_id_map: None,
                            partial_counts: Some(current_counts.clone()),
                            error_details: None,
                        }),
                    ))),
                },
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
        Ok(run) => match state.db.insert_run(&run).await {
            Ok(_) => (
                StatusCode::OK,
                Json(ApiResponse::ok("Run ingested successfully")),
            ),
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
        let (test_entity, test_result) = create_test_from_dto(dto.run_id, item);

        if let Err(e) = state.db.insert_test(&test_result).await {
            error!("Failed to ingest test: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest test: {}", e))),
            );
        }

        // Check for flakiness
        check_and_record_flakiness(&state.db, &test_entity).await;

        // Check for baseline drift
        check_baseline_drift(&state.db, &state.metrics, &test_entity).await;

        // Record metrics
        let labels = TestLabels {
            name: test_entity.name.clone(),
            suite: test_entity.suite.clone(),
            status: format!("{:?}", test_entity.status).to_lowercase(),
        };
        state
            .metrics
            .test_duration
            .get_or_create(&labels)
            .observe(test_entity.duration_ms as f64 / 1000.0);
        state.metrics.tests_total.get_or_create(&labels).inc();

        match test_entity.status {
            TestStatus::Pass => {
                state.metrics.tests_passed.get_or_create(&labels).inc();
            }
            TestStatus::Fail => {
                state.metrics.tests_failed.get_or_create(&labels).inc();
            }
            _ => {}
        }
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

                match state
                    .db
                    .find_test_by_name(&dto.run_id.to_string(), test_name)
                    .await
                {
                    Ok(Some(id_str)) => match EntityId::from_string(&id_str) {
                        Ok(id) => {
                            info!("Resolved test_id {} for test '{}'", id, test_name);
                            id
                        }
                        Err(_) => {
                            error!("Invalid ID in DB for test '{}'", test_name);
                            return (
                                StatusCode::INTERNAL_SERVER_ERROR,
                                Json(ApiResponse::error("Invalid ID in database")),
                            );
                        }
                    },
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

        if let Err(e) = state.db.insert_signal(&signal).await {
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

                match state
                    .db
                    .find_test_by_name(&dto.run_id.to_string(), test_name)
                    .await
                {
                    Ok(Some(id_str)) => match EntityId::from_string(&id_str) {
                        Ok(id) => {
                            info!("Resolved test_id {} for test '{}'", id, test_name);
                            id
                        }
                        Err(_) => {
                            error!("Invalid ID in DB for test '{}'", test_name);
                            return (
                                StatusCode::INTERNAL_SERVER_ERROR,
                                Json(ApiResponse::error("Invalid ID in database")),
                            );
                        }
                    },
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

        if let Err(e) = state.db.insert_artifact(&artifact).await {
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

    if let Err(e) = state.db.insert_run(&run).await {
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
        let (test_entity, test_result) = create_test_from_dto(batch.run.run_id, test_item);

        // Store test_name -> test_id mapping for later use
        test_id_map.insert(test_entity.name.clone(), test_entity.id);

        if let Err(e) = state.db.insert_test(&test_result).await {
            error!("Failed to ingest test '{}': {}", test_entity.name, e);
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

        // Check for flakiness
        check_and_record_flakiness(&state.db, &test_entity).await;

        // Check for baseline drift
        check_baseline_drift(&state.db, &state.metrics, &test_entity).await;

        // Record metrics
        let labels = TestLabels {
            name: test_entity.name.clone(),
            suite: test_entity.suite.clone(),
            status: format!("{:?}", test_entity.status).to_lowercase(),
        };
        state
            .metrics
            .test_duration
            .get_or_create(&labels)
            .observe(test_entity.duration_ms as f64 / 1000.0);
        state.metrics.tests_total.get_or_create(&labels).inc();

        match test_entity.status {
            TestStatus::Pass => {
                state.metrics.tests_passed.get_or_create(&labels).inc();
            }
            TestStatus::Fail => {
                state.metrics.tests_failed.get_or_create(&labels).inc();
            }
            _ => {}
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
        )
        .await
        {
            Ok(id) => id,
            Err(boxed_resp) => return *boxed_resp,
        };

        let signal = create_signal_from_dto(batch.run.run_id, test_id, signal_item);

        if let Err(e) = state.db.insert_signal(&signal).await {
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
        )
        .await
        {
            Ok(id) => id,
            Err(boxed_resp) => return *boxed_resp,
        };

        let artifact = create_artifact_from_dto(batch.run.run_id, test_id, artifact_item);

        if let Err(e) = state.db.insert_artifact(&artifact).await {
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
