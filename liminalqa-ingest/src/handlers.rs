//! HTTP request handlers

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::*, facts::*};
use liminalqa_db::query::{Query, QueryResult};
use serde::{Deserialize, Serialize};
use tracing::{error, info};

use crate::{ApiResponse, AppState};

/// POST /ingest/run — Ingest a test run
#[derive(Debug, Deserialize)]
pub struct RunEnvelope {
    pub run: Run,
}

pub async fn ingest_run(
    State(state): State<AppState>,
    Json(envelope): Json<RunEnvelope>,
) -> impl IntoResponse {
    info!("Ingesting run: id={}", envelope.run.id);

    match state.db.put_run(&envelope.run) {
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
pub struct TestsEnvelope {
    pub tests: Vec<Test>,
}

pub async fn ingest_tests(
    State(state): State<AppState>,
    Json(envelope): Json<TestsEnvelope>,
) -> impl IntoResponse {
    info!("Ingesting {} tests", envelope.tests.len());

    for test in &envelope.tests {
        if let Err(e) = state.db.put_test(test) {
            error!("Failed to ingest test {}: {}", test.id, e);
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
            envelope.tests.len()
        ))),
    )
}

/// POST /ingest/signals — Ingest signals
#[derive(Debug, Deserialize)]
pub struct SignalsEnvelope {
    pub signals: Vec<Signal>,
}

pub async fn ingest_signals(
    State(state): State<AppState>,
    Json(envelope): Json<SignalsEnvelope>,
) -> impl IntoResponse {
    info!("Ingesting {} signals", envelope.signals.len());

    for signal in &envelope.signals {
        if let Err(e) = state.db.put_signal(signal) {
            error!("Failed to ingest signal {}: {}", signal.id, e);
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
            envelope.signals.len()
        ))),
    )
}

/// POST /ingest/artifacts — Ingest artifacts
#[derive(Debug, Deserialize)]
pub struct ArtifactsEnvelope {
    pub artifacts: Vec<Artifact>,
}

pub async fn ingest_artifacts(
    State(state): State<AppState>,
    Json(envelope): Json<ArtifactsEnvelope>,
) -> impl IntoResponse {
    info!("Ingesting {} artifacts", envelope.artifacts.len());

    for artifact in &envelope.artifacts {
        if let Err(e) = state.db.put_artifact(artifact) {
            error!("Failed to ingest artifact {}: {}", artifact.id, e);
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
            envelope.artifacts.len()
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
