//! HTTP request handlers

use axum::{extract::{State, Query}, http::StatusCode, response::IntoResponse, Json};
use chrono::Utc;
use liminalqa_core::types::{EntityId, new_entity_id};
use liminalqa_db::models::*;
use serde::{Deserialize, Serialize};
use tracing::{error, info};

use crate::{ApiResponse, AppState};

// --- DTOs ---

#[derive(Debug, Serialize, Deserialize)]
pub struct RunDto {
    pub run_id: EntityId,
    pub build_id: EntityId,
    pub plan_name: String,
    pub env: serde_json::Value,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub runner_version: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TestsDto {
    pub run_id: EntityId,
    pub tests: Vec<TestDtoItem>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TestDtoItem {
    pub name: String,
    pub suite: String,
    pub status: String,
    pub duration_ms: Option<i32>,
    pub error: Option<serde_json::Value>,
    pub started_at: Option<chrono::DateTime<chrono::Utc>>,
    pub completed_at: Option<chrono::DateTime<chrono::Utc>>,
}

// Stub structs for Signals/Artifacts to keep API signature but we won't process them yet
#[derive(Debug, Serialize, Deserialize)]
pub struct SignalsDto {
    pub run_id: EntityId,
    pub signals: Vec<serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ArtifactsDto {
    pub run_id: EntityId,
    pub artifacts: Vec<serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct BatchIngestDto {
    pub run: RunDto,
    #[serde(default)]
    pub tests: Vec<TestDtoItem>,
    #[serde(default)]
    pub signals: Vec<serde_json::Value>,
    #[serde(default)]
    pub artifacts: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
pub struct DriftQuery {
    pub name: String,
    pub suite: String,
    pub days: i32,
}

#[derive(Deserialize)]
pub struct LimitQuery {
    pub limit: Option<i64>,
}

// --- Helpers ---

fn dto_to_db_run(dto: &RunDto) -> TestRun {
    TestRun {
        id: dto.run_id.to_string(),
        build_id: Some(dto.build_id.to_string()),
        plan_name: dto.plan_name.clone(),
        status: "running".to_string(),
        started_at: dto.started_at,
        completed_at: None,
        duration_ms: None,
        environment: Some(dto.env.clone()),
        metadata: None,
        created_at: Utc::now(),
        protocol_version: None,
        self_resonance_score: None,
        world_resonance_score: None,
        overall_alignment_score: None,
    }
}

fn dto_to_db_test(run_id: &str, item: &TestDtoItem) -> TestResult {
    TestResult {
        id: new_entity_id().to_string(),
        run_id: run_id.to_string(),
        name: item.name.clone(),
        suite: item.suite.clone(),
        status: item.status.clone(),
        duration_ms: item.duration_ms.unwrap_or(0),
        error_message: item.error.as_ref().map(|v| v.to_string()),
        stack_trace: None,
        metadata: None,
        executed_at: item.started_at.unwrap_or_else(Utc::now),
        created_at: Utc::now(),
        protocol_metrics: None,
    }
}

// --- Handlers ---

pub async fn ingest_run(
    State(state): State<AppState>,
    Json(dto): Json<RunDto>,
) -> impl IntoResponse {
    info!("Ingesting run: id={}", dto.run_id);
    let run = dto_to_db_run(&dto);

    match state.db.insert_run(&run).await {
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
    }
}

pub async fn ingest_tests(
    State(state): State<AppState>,
    Json(dto): Json<TestsDto>,
) -> impl IntoResponse {
    info!("Ingesting {} tests", dto.tests.len());

    for item in &dto.tests {
        let test = dto_to_db_test(&dto.run_id.to_string(), item);

        // TODO: Flakiness check and baseline drift check using new DB

        if let Err(e) = state.db.insert_test(&test).await {
            error!("Failed to ingest test: {}", e);
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest test: {}", e))),
            );
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
    State(_state): State<AppState>,
    Json(_dto): Json<SignalsDto>,
) -> impl IntoResponse {
    // Signals currently not supported in new schema
    (
        StatusCode::OK,
        Json(ApiResponse::ok("Signals ignored (Phase 4 schema)")),
    )
}

pub async fn ingest_artifacts(
    State(_state): State<AppState>,
    Json(_dto): Json<ArtifactsDto>,
) -> impl IntoResponse {
    // Artifacts currently not supported in new schema
    (
        StatusCode::OK,
        Json(ApiResponse::ok("Artifacts ignored (Phase 4 schema)")),
    )
}

pub async fn ingest_batch(
    State(state): State<AppState>,
    Json(batch): Json<BatchIngestDto>,
) -> impl IntoResponse {
    // 1. Ingest Run
    let run = dto_to_db_run(&batch.run);
    if let Err(e) = state.db.insert_run(&run).await {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiResponse::error(format!("Failed to ingest run: {}", e))),
        );
    }

    // 2. Ingest Tests
    let mut tests_count = 0;
    for item in &batch.tests {
        let test = dto_to_db_test(&run.id, item);
        if let Err(e) = state.db.insert_test(&test).await {
             return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!("Failed to ingest test: {}", e))),
            );
        }
        tests_count += 1;
    }

    (
        StatusCode::OK,
        Json(ApiResponse::ok(format!(
            "Batch ingested: Run {}, Tests {} (Signals/Artifacts ignored)",
            run.id, tests_count
        ))),
    )
}

pub async fn get_drift_data(
    State(state): State<AppState>,
    Query(query): Query<DriftQuery>,
) -> impl IntoResponse {
    match state.db.get_drift_data(&query.name, &query.suite, query.days).await {
        Ok(data) => (StatusCode::OK, Json(data)).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiResponse::error(e.to_string()))
        ).into_response()
    }
}

pub async fn get_protocol_quality(
    State(state): State<AppState>,
    Query(query): Query<LimitQuery>,
) -> impl IntoResponse {
    match state.db.get_protocol_quality_view(query.limit.unwrap_or(50)).await {
        Ok(data) => (StatusCode::OK, Json(data)).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiResponse::error(e.to_string()))
        ).into_response()
    }
}

pub async fn query_handler(
    State(_state): State<AppState>,
    Json(_query): Json<serde_json::Value>,
) -> impl IntoResponse {
    // Stub
    (StatusCode::OK, Json(serde_json::json!([])))
}
