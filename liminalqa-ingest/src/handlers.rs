//! HTTP request handlers

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::*, temporal::BiTemporalTime, types::*};
use liminalqa_db::query::{Query, QueryResult};
use serde::{Deserialize, Serialize};
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
                let name = match item.test_name.as_ref() {
                    Some(n) => n,
                    None => {
                        return (
                            StatusCode::BAD_REQUEST,
                            Json(ApiResponse::error("Each signal must have either test_id or test_name")),
                        );
                    }
                };

                match state.db.find_test_by_name(dto.run_id, name) {
                    Ok(Some(id)) => id,
                    Ok(None) => {
                        // Fallback: create placeholder
                        match state.db.create_placeholder_test(dto.run_id, name) {
                            Ok(id) => id,
                            Err(e) => {
                                error!("Failed to create placeholder test: {}", e);
                                return (
                                    StatusCode::INTERNAL_SERVER_ERROR,
                                    Json(ApiResponse::error(format!(
                                        "Failed to create placeholder test: {}", e
                                    ))),
                                );
                            }
                        }
                    }
                    Err(e) => {
                        error!("DB error finding test: {}", e);
                        return (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(ApiResponse::error(format!(
                                "DB error finding test: {}", e
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
                let name = match item.test_name.as_ref() {
                    Some(n) => n,
                    None => {
                        return (
                            StatusCode::BAD_REQUEST,
                            Json(ApiResponse::error("Each artifact must have either test_id or test_name")),
                        );
                    }
                };

                match state.db.find_test_by_name(dto.run_id, name) {
                    Ok(Some(id)) => id,
                    Ok(None) => {
                         // Fallback: create placeholder
                         match state.db.create_placeholder_test(dto.run_id, name) {
                             Ok(id) => id,
                             Err(e) => {
                                 error!("Failed to create placeholder test: {}", e);
                                 return (
                                     StatusCode::INTERNAL_SERVER_ERROR,
                                     Json(ApiResponse::error(format!(
                                         "Failed to create placeholder test: {}", e
                                     ))),
                                 );
                             }
                         }
                    }
                    Err(e) => {
                        error!("DB error finding test: {}", e);
                        return (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(ApiResponse::error(format!(
                                "DB error finding test: {}", e
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

/// POST /ingest/batch — Batch ingestion
#[derive(Debug, Deserialize)]
pub struct BatchIngestDto {
    pub run_id: Option<EntityId>,
    pub run: Option<RunDto>,
    pub tests: Option<Vec<TestDtoItem>>,
    pub signals: Option<Vec<SignalDtoItem>>,
    pub artifacts: Option<Vec<ArtifactDtoItem>>,
}

#[derive(Debug, Serialize)]
pub struct BatchIngestResponse {
    pub ok: bool,
    pub counts: BatchCounts,
    pub message: Option<String>,
}

#[derive(Debug, Serialize, Default)]
pub struct BatchCounts {
    pub tests: usize,
    pub signals: usize,
    pub artifacts: usize,
}

pub async fn ingest_batch(
    State(state): State<AppState>,
    Json(dto): Json<BatchIngestDto>,
) -> impl IntoResponse {
    info!("Ingesting batch");

    // TODO: Implement atomic transactions. Current implementation is sequential
    // and may leave DB in inconsistent state if one item fails.
    // See roadmap: Atomic transaction for entire batch.

    let run_id = if let Some(ref run) = dto.run {
        run.run_id
    } else if let Some(id) = dto.run_id {
        id
    } else {
         return (
            StatusCode::BAD_REQUEST,
            Json(BatchIngestResponse {
                ok: false,
                counts: BatchCounts::default(),
                message: Some("Either run object or run_id must be provided".to_string()),
            }),
        ).into_response();
    };

    // 1. Ingest Run
    if let Some(run_dto) = dto.run {
         let env = match serde_json::from_value::<std::collections::HashMap<String, String>>(run_dto.env) {
            Ok(env) => env,
            Err(e) => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(BatchIngestResponse {
                        ok: false,
                        counts: BatchCounts::default(),
                        message: Some(format!("Invalid env format: {}", e)),
                    }),
                ).into_response();
            }
        };

        let run = Run {
            id: run_dto.run_id,
            build_id: run_dto.build_id,
            plan_name: run_dto.plan_name,
            env,
            started_at: run_dto.started_at,
            ended_at: None,
            runner_version: run_dto.runner_version.unwrap_or_else(|| "unknown".to_string()),
            liminal_os_version: None,
            created_at: BiTemporalTime::now(),
        };

        if let Err(e) = state.db.put_run(&run) {
             return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(BatchIngestResponse {
                    ok: false,
                    counts: BatchCounts::default(),
                    message: Some(format!("Failed to ingest run: {}", e)),
                }),
            ).into_response();
        }
    }

    let mut counts = BatchCounts::default();

    // 2. Ingest Tests
    if let Some(tests) = dto.tests {
        for item in tests {
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
                run_id,
                name: item.name.clone(),
                suite: item.suite,
                guidance: item.guidance.unwrap_or_default(),
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
                    Json(BatchIngestResponse {
                        ok: false,
                        counts,
                        message: Some(format!("Failed to ingest test: {}", e)),
                    }),
                ).into_response();
            }
            counts.tests += 1;
        }
    }

    // 3. Ingest Signals
    if let Some(signals) = dto.signals {
        for item in signals {
             // Resolve test_id
            let test_id = match item.test_id {
                Some(id) => id,
                None => {
                    let name = match item.test_name {
                        Some(ref n) => n,
                        None => {
                             return (
                                StatusCode::BAD_REQUEST,
                                Json(BatchIngestResponse {
                                    ok: false,
                                    counts,
                                    message: Some("Signal missing test_id or test_name".to_string()),
                                }),
                            ).into_response();
                        }
                    };

                    match state.db.find_test_by_name(run_id, name) {
                        Ok(Some(id)) => id,
                        Ok(None) => {
                            // Fallback: create placeholder
                            match state.db.create_placeholder_test(run_id, name) {
                                Ok(id) => id,
                                Err(e) => {
                                     return (
                                        StatusCode::INTERNAL_SERVER_ERROR,
                                        Json(BatchIngestResponse {
                                            ok: false,
                                            counts,
                                            message: Some(format!("Failed to create placeholder test: {}", e)),
                                        }),
                                    ).into_response();
                                }
                            }
                        }
                        Err(e) => {
                             return (
                                StatusCode::INTERNAL_SERVER_ERROR,
                                Json(BatchIngestResponse {
                                    ok: false,
                                    counts,
                                    message: Some(format!("DB error finding test: {}", e)),
                                }),
                            ).into_response();
                        }
                    }
                }
            };

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

            let signal = Signal {
                id: EntityId::new(),
                run_id,
                test_id,
                signal_type,
                timestamp: item.at,
                latency_ms: item.latency_ms,
                payload_ref: None,
                metadata,
                created_at: BiTemporalTime::now(),
            };

            if let Err(e) = state.db.put_signal(&signal) {
                 return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(BatchIngestResponse {
                        ok: false,
                        counts,
                        message: Some(format!("Failed to ingest signal: {}", e)),
                    }),
                ).into_response();
            }
            counts.signals += 1;
        }
    }

    // 4. Ingest Artifacts
    if let Some(artifacts) = dto.artifacts {
        for item in artifacts {
            // Resolve test_id
             let test_id = match item.test_id {
                Some(id) => id,
                None => {
                    let name = match item.test_name {
                        Some(ref n) => n,
                        None => {
                             return (
                                StatusCode::BAD_REQUEST,
                                Json(BatchIngestResponse {
                                    ok: false,
                                    counts,
                                    message: Some("Artifact missing test_id or test_name".to_string()),
                                }),
                            ).into_response();
                        }
                    };

                    match state.db.find_test_by_name(run_id, name) {
                        Ok(Some(id)) => id,
                        Ok(None) => {
                             // Fallback: create placeholder
                             match state.db.create_placeholder_test(run_id, name) {
                                 Ok(id) => id,
                                 Err(e) => {
                                      return (
                                         StatusCode::INTERNAL_SERVER_ERROR,
                                         Json(BatchIngestResponse {
                                             ok: false,
                                             counts,
                                             message: Some(format!("Failed to create placeholder test: {}", e)),
                                         }),
                                     ).into_response();
                                 }
                             }
                        }
                        Err(e) => {
                             return (
                                StatusCode::INTERNAL_SERVER_ERROR,
                                Json(BatchIngestResponse {
                                    ok: false,
                                    counts,
                                    message: Some(format!("DB error finding test: {}", e)),
                                }),
                            ).into_response();
                        }
                    }
                }
            };

            let artifact_type = match item.kind.to_lowercase().as_str() {
                "screenshot" => ArtifactType::Screenshot,
                "apiresponse" => ArtifactType::ApiResponse,
                "wsmessage" => ArtifactType::WsMessage,
                "grpctrace" => ArtifactType::GrpcTrace,
                "log" => ArtifactType::Log,
                "video" => ArtifactType::Video,
                _ => ArtifactType::Trace,
            };

            let artifact = Artifact {
                id: EntityId::new(),
                run_id,
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
                 return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(BatchIngestResponse {
                        ok: false,
                        counts,
                        message: Some(format!("Failed to ingest artifact: {}", e)),
                    }),
                ).into_response();
            }
            counts.artifacts += 1;
        }
    }

    if let Err(e) = state.db.flush() {
        error!("Failed to flush db: {}", e);
    }

    (
        StatusCode::OK,
        Json(BatchIngestResponse {
            ok: true,
            counts,
            message: None,
        }),
    ).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use liminalqa_db::LiminalDB;

    fn setup_state_with_dir() -> (AppState, tempfile::TempDir) {
        let temp_dir = tempfile::tempdir().unwrap();
        let db = LiminalDB::open(temp_dir.path()).unwrap();
        (AppState {
            db: Arc::new(db),
            auth_token: None,
        }, temp_dir)
    }

    #[tokio::test]
    async fn test_ingest_batch() {
        let (state, _temp_dir) = setup_state_with_dir();
        let run_id = EntityId::new();

        let batch = BatchIngestDto {
            run_id: Some(run_id),
            run: Some(RunDto {
                run_id,
                build_id: EntityId::new(),
                plan_name: "test_plan".to_string(),
                env: serde_json::json!({"OS": "Linux"}),
                started_at: chrono::Utc::now(),
                runner_version: None,
            }),
            tests: Some(vec![TestDtoItem {
                name: "test_1".to_string(),
                suite: "suite_1".to_string(),
                guidance: None,
                status: "Pass".to_string(),
                duration_ms: Some(100),
                error: None,
                started_at: None,
                completed_at: None,
            }]),
            signals: Some(vec![SignalDtoItem {
                test_id: None,
                test_name: Some("test_1".to_string()),
                kind: "ui".to_string(),
                latency_ms: Some(50),
                value: None,
                meta: None,
                at: chrono::Utc::now(),
            }]),
            artifacts: None,
        };

        // Invoke handler directly
        let response = ingest_batch(
            State(state.clone()),
            Json(batch)
        ).await.into_response();

        assert_eq!(response.status(), StatusCode::OK);

        // Verify DB
        // Check test exists
        let test_id = state.db.find_test_by_name(run_id, "test_1").unwrap();
        assert!(test_id.is_some());

        // Check signal exists
        let signals = state.db.get_entities_by_type(EntityType::Signal).unwrap();
        assert_eq!(signals.len(), 1);
        let signal: Signal = state.db.get_entity(signals[0]).unwrap().unwrap();
        assert_eq!(signal.test_id, test_id.unwrap());
    }
}
