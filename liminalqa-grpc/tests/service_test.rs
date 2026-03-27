//! Integration tests for MyIngestService gRPC handlers.
//!
//! Tests call the service methods directly (no network) using a real LiminalDB
//! backed by a temp directory.
//!
//! Note: stream_signals requires a full gRPC channel to test end-to-end.
//! Its internals (signal mapping, DB writes) are covered by storage layer tests.

use liminalqa_core::types::EntityId;
use liminalqa_db::LiminalDB;
use liminalqa_grpc::{
    server::MyIngestService, IngestRunRequest, IngestTestsRequest, IngestTestsResponse,
};
use std::sync::Arc;
use tempfile::TempDir;
use tonic::Request;

// Re-export the proto Test message under a distinct name to avoid clash
use liminalqa_grpc::liminalqa::v1::Test as ProtoTest;

fn make_service() -> (MyIngestService, TempDir) {
    let dir = TempDir::new().unwrap();
    let db = LiminalDB::open(dir.path()).unwrap();
    (MyIngestService::new(Arc::new(db)), dir)
}

fn now_ms() -> i64 {
    chrono::Utc::now().timestamp_millis()
}

// ---------------------------------------------------------------------------
// IngestRun
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_ingest_run_returns_ulid() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let req = IngestRunRequest {
        build_id: EntityId::new().to_string(),
        plan_name: "ci-smoke".to_string(),
        env: r#"{"CI":"true"}"#.to_string(),
        started_at: now_ms(),
        ended_at: None,
        runner_version: "0.1.0".to_string(),
        liminal_os_version: None,
    };

    let resp = svc.ingest_run(Request::new(req)).await.unwrap();
    let run_id = resp.into_inner().run_id;

    assert_eq!(run_id.len(), 26, "run_id should be a 26-char ULID");
    assert!(
        EntityId::from_string(&run_id).is_ok(),
        "run_id must parse as ULID"
    );
}

#[tokio::test]
async fn test_ingest_run_invalid_build_id() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let req = IngestRunRequest {
        build_id: "not-a-ulid".to_string(),
        plan_name: "plan".to_string(),
        env: "{}".to_string(),
        started_at: now_ms(),
        ended_at: None,
        runner_version: "0.1.0".to_string(),
        liminal_os_version: None,
    };

    let err = svc.ingest_run(Request::new(req)).await.unwrap_err();
    assert_eq!(err.code(), tonic::Code::InvalidArgument);
    assert!(err.message().contains("build_id"));
}

#[tokio::test]
async fn test_ingest_run_invalid_env_json() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let req = IngestRunRequest {
        build_id: EntityId::new().to_string(),
        plan_name: "plan".to_string(),
        env: "INVALID_JSON".to_string(),
        started_at: now_ms(),
        ended_at: None,
        runner_version: "0.1.0".to_string(),
        liminal_os_version: None,
    };

    let err = svc.ingest_run(Request::new(req)).await.unwrap_err();
    assert_eq!(err.code(), tonic::Code::InvalidArgument);
    assert!(err.message().contains("env"));
}

// ---------------------------------------------------------------------------
// IngestTests
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_ingest_tests_stores_all() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let run_id = EntityId::new().to_string();
    let ts = now_ms();

    let req = IngestTestsRequest {
        run_id: run_id.clone(),
        tests: vec![
            ProtoTest {
                id: None,
                name: "test_login".to_string(),
                suite: "auth".to_string(),
                guidance: "User can log in".to_string(),
                status: "pass".to_string(),
                duration_ms: 120,
                error_message: None,
                started_at: ts,
                completed_at: ts + 120,
            },
            ProtoTest {
                id: None,
                name: "test_logout".to_string(),
                suite: "auth".to_string(),
                guidance: "User can log out".to_string(),
                status: "fail".to_string(),
                duration_ms: 55,
                error_message: Some("AssertionError: expected redirect".to_string()),
                started_at: ts,
                completed_at: ts + 55,
            },
        ],
    };

    let resp: IngestTestsResponse = svc
        .ingest_tests(Request::new(req))
        .await
        .unwrap()
        .into_inner();

    assert_eq!(resp.processed_count, 2);
    assert_eq!(resp.failed_count, 0);
    assert!(resp.failed_ids.is_empty());
}

#[tokio::test]
async fn test_ingest_tests_all_statuses_mapped() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let run_id = EntityId::new().to_string();
    let ts = now_ms();

    let statuses = [
        "pass", "fail", "skip", "xfail", "flake", "timeout", "unknown",
    ];

    let tests: Vec<ProtoTest> = statuses
        .iter()
        .map(|&s| ProtoTest {
            id: None,
            name: format!("test_{}", s),
            suite: "suite".to_string(),
            guidance: String::new(),
            status: s.to_string(),
            duration_ms: 10,
            error_message: None,
            started_at: ts,
            completed_at: ts + 10,
        })
        .collect();

    let resp = svc
        .ingest_tests(Request::new(IngestTestsRequest { run_id, tests }))
        .await
        .unwrap()
        .into_inner();

    assert_eq!(resp.processed_count, statuses.len() as i32);
    assert_eq!(resp.failed_count, 0);
}

#[tokio::test]
async fn test_ingest_tests_with_explicit_id() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let run_id = EntityId::new().to_string();
    let test_id = EntityId::new().to_string();
    let ts = now_ms();

    let req = IngestTestsRequest {
        run_id,
        tests: vec![ProtoTest {
            id: Some(test_id.clone()),
            name: "test_with_id".to_string(),
            suite: "suite".to_string(),
            guidance: String::new(),
            status: "pass".to_string(),
            duration_ms: 10,
            error_message: None,
            started_at: ts,
            completed_at: ts + 10,
        }],
    };

    let resp = svc
        .ingest_tests(Request::new(req))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(resp.processed_count, 1);
    assert_eq!(resp.failed_count, 0);
}

#[tokio::test]
async fn test_ingest_tests_invalid_run_id() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let err = svc
        .ingest_tests(Request::new(IngestTestsRequest {
            run_id: "bad-id".to_string(),
            tests: vec![],
        }))
        .await
        .unwrap_err();

    assert_eq!(err.code(), tonic::Code::InvalidArgument);
}

// ---------------------------------------------------------------------------
// Helper logic unit tests (signal/status mapping)
// ---------------------------------------------------------------------------

/// Verify that all recognised status strings are handled without panic.
/// Unknown values fall through to Skip.
#[tokio::test]
async fn test_status_mapping_coverage() {
    let (svc, _dir) = make_service();

    use liminalqa_grpc::IngestService;
    let run_id = EntityId::new().to_string();
    let ts = now_ms();

    let statuses = [
        "pass",
        "passed",
        "success",
        "fail",
        "failed",
        "error",
        "xfail",
        "flake",
        "flaky",
        "timeout",
        "skip",
        "anything_else_maps_to_skip",
    ];

    let tests: Vec<ProtoTest> = statuses
        .iter()
        .map(|&s| ProtoTest {
            id: None,
            name: format!("test_{}", s),
            suite: "suite".to_string(),
            guidance: String::new(),
            status: s.to_string(),
            duration_ms: 1,
            error_message: None,
            started_at: ts,
            completed_at: ts + 1,
        })
        .collect();

    let count = tests.len() as i32;
    let resp: IngestTestsResponse = svc
        .ingest_tests(Request::new(IngestTestsRequest { run_id, tests }))
        .await
        .unwrap()
        .into_inner();

    assert_eq!(resp.processed_count, count);
    assert_eq!(resp.failed_count, 0);
}
