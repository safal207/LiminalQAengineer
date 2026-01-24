#![cfg(test)]
#![allow(clippy::disallowed_methods)]
#![allow(unused_imports)]

use axum::{
    body::Body,
    http::{Request, StatusCode},
    routing::post,
    Router,
};
use liminalqa_core::types::EntityId;
use liminalqa_db::LiminalDB;
use liminalqa_ingest::{
    handlers::{
        ingest_batch, ArtifactDtoItem, BatchIngestDto, BatchIngestResponse, RunDto, SignalDtoItem,
        TestDtoItem,
    },
    AppState,
};
use std::sync::Arc;
use tower::util::ServiceExt; // for `oneshot`

#[tokio::test]
async fn test_batch_ingestion_full_flow() {
    // Setup database
    let db_dir = tempfile::tempdir().unwrap();
    let db = LiminalDB::open(db_dir.path()).unwrap();
    let state = AppState {
        db: Arc::new(db),
        auth_token: None,
    };

    // Setup Router
    let app = Router::new()
        .route("/ingest/batch", post(ingest_batch))
        .with_state(state);

    // Prepare DTO
    let batch = BatchIngestDto {
        run: RunDto {
            run_id: EntityId::new(),
            build_id: EntityId::new(),
            plan_name: "smoke".to_string(),
            env: serde_json::json!({}),
            started_at: chrono::Utc::now(),
            runner_version: Some("1.0.0".to_string()),
        },
        tests: vec![
            TestDtoItem {
                name: "test_a".to_string(),
                suite: "suite1".to_string(),
                status: "pass".to_string(),
                duration_ms: Some(100),
                guidance: None,
                error: None,
                started_at: None,
                completed_at: None,
            },
            TestDtoItem {
                name: "test_b".to_string(),
                suite: "suite1".to_string(),
                status: "fail".to_string(),
                duration_ms: Some(200),
                guidance: None,
                error: None,
                started_at: None,
                completed_at: None,
            },
        ],
        signals: vec![SignalDtoItem {
            test_id: None,
            test_name: Some("test_a".to_string()),
            kind: "api".to_string(),
            latency_ms: Some(50),
            at: chrono::Utc::now(),
            value: None,
            meta: None,
        }],
        artifacts: vec![ArtifactDtoItem {
            test_id: None,
            test_name: Some("test_b".to_string()),
            kind: "screenshot".to_string(),
            path: "/screenshots/fail.png".to_string(),
            path_sha256: "abc123456".to_string(),
            size_bytes: Some(1024),
            mime_type: Some("image/png".to_string()),
        }],
    };

    // Send Request
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/ingest/batch")
                .header("Content-Type", "application/json")
                .body(Body::from(serde_json::to_string(&batch).unwrap()))
                .unwrap(),
        )
        .await
        .unwrap();

    // Assert Status
    assert_eq!(response.status(), StatusCode::OK);

    // Parse Response Body
    let body_bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let body: BatchIngestResponse = serde_json::from_slice(&body_bytes).unwrap();

    // Assert Response Content
    assert!(body.ok);
    assert_eq!(body.counts.run, 1);
    assert_eq!(body.counts.tests, 2);
    assert_eq!(body.counts.signals, 1);
    assert_eq!(body.counts.artifacts, 1);

    let map = body.test_id_map.expect("test_id_map should be present");
    assert!(map.contains_key("test_a"));
    assert!(map.contains_key("test_b"));
}

#[tokio::test]
async fn test_batch_ingestion_partial_failure() {
    // Setup database
    let db_dir = tempfile::tempdir().unwrap();
    let db = LiminalDB::open(db_dir.path()).unwrap();
    let state = AppState {
        db: Arc::new(db),
        auth_token: None,
    };

    let app = Router::new()
        .route("/ingest/batch", post(ingest_batch))
        .with_state(state);

    // Prepare Invalid DTO (Missing test reference for signal)
    let batch = BatchIngestDto {
        run: RunDto {
            run_id: EntityId::new(),
            build_id: EntityId::new(),
            plan_name: "smoke".to_string(),
            env: serde_json::json!({}),
            started_at: chrono::Utc::now(),
            runner_version: Some("1.0.0".to_string()),
        },
        tests: vec![],
        signals: vec![SignalDtoItem {
            test_id: None,
            test_name: Some("non_existent_test".to_string()),
            kind: "api".to_string(),
            latency_ms: Some(50),
            at: chrono::Utc::now(),
            value: None,
            meta: None,
        }],
        artifacts: vec![],
    };

    // Send Request
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/ingest/batch")
                .header("Content-Type", "application/json")
                .body(Body::from(serde_json::to_string(&batch).unwrap()))
                .unwrap(),
        )
        .await
        .unwrap();

    // Should return 404 because test not found
    assert_eq!(response.status(), StatusCode::NOT_FOUND);

    let body_bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .unwrap();
    let body: BatchIngestResponse = serde_json::from_slice(&body_bytes).unwrap();

    assert!(!body.ok);
    // Partial counts should show run was ingested
    let partial_counts = body.partial_counts.expect("Should have partial counts");
    assert_eq!(partial_counts.run, 1);
    assert_eq!(partial_counts.signals, 0);
}
