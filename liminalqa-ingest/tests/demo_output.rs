//! Demo integration test — показывает реальный JSON из новых эндпоинтов:
//!
//!   GET /api/resonance/signals/:run_id?env=prod&cpu=85
//!   GET /api/causality/:run_id/:signal_id?depth=3
//!   GET /api/triage
//!   GET /api/resonance/flaky
//!
//! Запуск:
//!   cargo test -p liminalqa-ingest --test demo_output -- --nocapture

#![cfg(test)]
#![allow(clippy::disallowed_methods)]

use axum::{
    body::Body,
    http::{Request, StatusCode},
    routing::{get, post},
    Router,
};
use liminalqa_core::types::EntityId;
use liminalqa_db::LiminalDB;
use liminalqa_ingest::{
    alerting::AlertManager,
    handlers::{ingest_batch, BatchIngestDto, RunDto, SignalDtoItem, TestDtoItem},
    resonance::{get_causality_chain, get_flaky_tests, get_signals_by_run, get_triage},
    AppState, RateLimiter,
};
use std::sync::Arc;
use tower::util::ServiceExt;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn make_app(db: LiminalDB) -> Router {
    let metrics = Arc::new(liminalqa_core::metrics::MetricsRegistry::new());
    let state = AppState {
        db: Arc::new(db),
        auth_token: None,
        metrics,
        rate_limiter: Arc::new(RateLimiter::new(10_000)),
        alerts: AlertManager::from_env(),
    };
    Router::new()
        .route("/ingest/batch", post(ingest_batch))
        .route("/api/resonance/signals/:run_id", get(get_signals_by_run))
        .route(
            "/api/causality/:run_id/:signal_id",
            get(get_causality_chain),
        )
        .route("/api/triage", get(get_triage))
        .route("/api/resonance/flaky", get(get_flaky_tests))
        .with_state(state)
}

async fn post_batch(app: &Router, batch: &BatchIngestDto) {
    let body = serde_json::to_vec(batch).unwrap();
    let req = Request::builder()
        .method("POST")
        .uri("/ingest/batch")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK, "ingest failed");
}

async fn get_json(app: &Router, url: &str) -> (StatusCode, serde_json::Value) {
    let req = Request::builder()
        .method("GET")
        .uri(url)
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
        .await
        .unwrap();
    let val: serde_json::Value = serde_json::from_slice(&bytes).unwrap_or(serde_json::Value::Null);
    (status, val)
}

fn section(title: &str) {
    println!("\n{}", "─".repeat(65));
    println!("  {title}");
    println!("{}\n", "─".repeat(65));
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

#[tokio::test]
async fn demo_all_analysis_endpoints() {
    let db_dir = tempfile::tempdir().unwrap();
    let db = LiminalDB::open(db_dir.path()).unwrap();
    let app = make_app(db);

    let run_id = EntityId::new();
    let build_id = EntityId::new();
    let now = chrono::Utc::now();

    // ------------------------------------------------------------------
    // Ingest run #1: API(250ms) → DB(3200ms at +800ms) → gRPC(80ms at +1200ms)
    //   auth/login   → Pass  120ms
    //   payments/charge → Fail 5100ms
    //   health/ping  → Pass   10ms
    // ------------------------------------------------------------------
    let batch = BatchIngestDto {
        run: RunDto {
            run_id,
            build_id,
            plan_name: "nightly-smoke".to_string(),
            env: serde_json::json!({
                "CI": "true",
                "LIMINALQA_ENV": "prod",
                "GITHUB_SHA": "abc123"
            }),
            started_at: now,
            runner_version: Some("1.0.0".to_string()),
        },
        tests: vec![
            TestDtoItem {
                name: "login".to_string(),
                suite: "auth".to_string(),
                guidance: None,
                status: "pass".to_string(),
                duration_ms: Some(120),
                error: None,
                started_at: Some(now),
                completed_at: Some(now + chrono::Duration::milliseconds(120)),
            },
            TestDtoItem {
                name: "charge".to_string(),
                suite: "payments".to_string(),
                guidance: None,
                status: "fail".to_string(),
                duration_ms: Some(5100),
                error: Some(serde_json::json!({"message": "timeout waiting for payment gateway"})),
                started_at: Some(now),
                completed_at: Some(now + chrono::Duration::milliseconds(5100)),
            },
            TestDtoItem {
                name: "ping".to_string(),
                suite: "health".to_string(),
                guidance: None,
                status: "pass".to_string(),
                duration_ms: Some(10),
                error: None,
                started_at: Some(now),
                completed_at: Some(now + chrono::Duration::milliseconds(10)),
            },
        ],
        signals: vec![
            SignalDtoItem {
                test_id: None,
                test_name: Some("charge".to_string()),
                kind: "api".to_string(),
                latency_ms: Some(250),
                value: None,
                meta: Some(serde_json::json!({"endpoint": "/api/auth/login", "status_code": 200})),
                at: now,
            },
            SignalDtoItem {
                test_id: None,
                test_name: Some("charge".to_string()),
                kind: "database".to_string(),
                latency_ms: Some(3200),
                value: None,
                meta: Some(serde_json::json!({"query": "SELECT * FROM payments", "rows": 42})),
                at: now + chrono::Duration::milliseconds(800),
            },
            SignalDtoItem {
                test_id: None,
                test_name: Some("charge".to_string()),
                kind: "grpc".to_string(),
                latency_ms: Some(80),
                value: None,
                meta: Some(serde_json::json!({"method": "PaymentService.Charge"})),
                at: now + chrono::Duration::milliseconds(1200),
            },
        ],
        artifacts: vec![],
    };

    post_batch(&app, &batch).await;

    // ------------------------------------------------------------------
    // 1. GET /api/resonance/signals/:run_id?env=prod&cpu=85
    // ------------------------------------------------------------------
    section("GET /api/resonance/signals/:run_id?env=prod&cpu=85");
    println!("Context: Prod environment, 85% CPU (high load → dampened importance)\n");

    let url = format!("/api/resonance/signals/{}?env=prod&cpu=85", run_id);
    let (status, json) = get_json(&app, &url).await;
    println!("HTTP {status}\n");

    println!("environment : {}", json["environment"]);
    println!(
        "filtered_latencies_ms (noise-filtered): {}",
        json["filtered_latencies_ms"]
    );
    println!("\nSignals ranked by adjusted_importance ↓");
    if let Some(signals) = json["signals"].as_array() {
        for s in signals {
            println!(
                "  {:9} latency={:>5}ms  base={:.3}  ×ctx={:.3}  →  adjusted={:.3}",
                s["signal_type"].as_str().unwrap_or("?"),
                s["latency_ms"].as_u64().unwrap_or(0),
                s["base_importance"].as_f64().unwrap_or(0.0),
                s["context_multiplier"].as_f64().unwrap_or(0.0),
                s["adjusted_importance"].as_f64().unwrap_or(0.0),
            );
        }
    }

    // Save first signal_id for causality demo
    let first_signal_id = json["signals"][0]["signal_id"]
        .as_str()
        .unwrap_or("MISSING")
        .to_string();

    // ------------------------------------------------------------------
    // 2. GET /api/causality/:run_id/:signal_id?depth=3
    // ------------------------------------------------------------------
    section(&format!(
        "GET /api/causality/:run_id/{}?depth=3",
        &first_signal_id[..8]
    ));
    println!("Walk: root API signal → DB → gRPC, exponential time-decay\n");

    let url = format!("/api/causality/{}/{}?depth=3", run_id, first_signal_id);
    let (status, json) = get_json(&app, &url).await;
    println!("HTTP {status}\n");

    println!("root_signal_id : {}", json["root_signal_id"]);
    println!("total_hops     : {}", json["total_hops"]);
    println!("max_depth      : {}", json["max_depth_reached"]);
    println!("\nNodes (depth-first):");
    if let Some(nodes) = json["nodes"].as_array() {
        for node in nodes {
            let indent = "  ".repeat(node["depth"].as_u64().unwrap_or(0) as usize + 1);
            let edges = node["edges"].as_array().map(|e| e.len()).unwrap_or(0);
            println!(
                "{}depth={} {:9}  causal_weight={:.4}  base_importance={:.3}  edges→{}",
                indent,
                node["depth"],
                node["signal_type"].as_str().unwrap_or("?"),
                node["causal_weight"].as_f64().unwrap_or(0.0),
                node["base_importance"].as_f64().unwrap_or(0.0),
                edges,
            );
            if let Some(edges) = node["edges"].as_array() {
                for edge in edges {
                    println!(
                        "{}  ↳ Δt={}ms  strength={:.4}",
                        indent,
                        edge["delta_ms"],
                        edge["strength"].as_f64().unwrap_or(0.0),
                    );
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // 3. Ingest 8 more runs to build triage history
    //    auth/login alternates pass/fail  → Flake
    //    payments/charge always fails     → KnownIssue (or NewBug if recent)
    //    health/ping always passes        → Stable
    // ------------------------------------------------------------------
    for i in 0..8u32 {
        let login_status = if i % 2 == 0 { "pass" } else { "fail" };
        let b = BatchIngestDto {
            run: RunDto {
                run_id: EntityId::new(),
                build_id,
                plan_name: "nightly-smoke".to_string(),
                env: serde_json::json!({"CI": "true"}),
                started_at: now + chrono::Duration::seconds(i as i64 * 3600),
                runner_version: Some("1.0.0".to_string()),
            },
            tests: vec![
                TestDtoItem {
                    name: "login".to_string(),
                    suite: "auth".to_string(),
                    guidance: None,
                    status: login_status.to_string(),
                    duration_ms: Some(100 + i as i32 * 20),
                    error: None,
                    started_at: Some(now),
                    completed_at: None,
                },
                TestDtoItem {
                    name: "charge".to_string(),
                    suite: "payments".to_string(),
                    guidance: None,
                    status: "fail".to_string(),
                    duration_ms: Some(5000),
                    error: None,
                    started_at: Some(now),
                    completed_at: None,
                },
                TestDtoItem {
                    name: "ping".to_string(),
                    suite: "health".to_string(),
                    guidance: None,
                    status: "pass".to_string(),
                    duration_ms: Some(10),
                    error: None,
                    started_at: Some(now),
                    completed_at: None,
                },
            ],
            signals: vec![],
            artifacts: vec![],
        };
        post_batch(&app, &b).await;
    }

    // ------------------------------------------------------------------
    // 4. GET /api/triage
    // ------------------------------------------------------------------
    section("GET /api/triage  (after 9 runs of history)");

    let (status, json) = get_json(&app, "/api/triage").await;
    println!("HTTP {status}\n");
    println!("total_analyzed: {}\n", json["total_analyzed"]);
    println!("{:<12} {:<9} {:<8} {:<8} runs", "suite/name", "verdict", "stab%", "flake");
    println!("{}", "─".repeat(55));
    if let Some(tests) = json["tests"].as_array() {
        for t in tests {
            println!(
                "{:<12} {:<9} {:>6.1}%  {:>6.3}  {}",
                format!(
                    "{}/{}",
                    t["suite"].as_str().unwrap_or("?"),
                    t["name"].as_str().unwrap_or("?")
                ),
                t["verdict"].as_str().unwrap_or("?"),
                t["stability_score"].as_f64().unwrap_or(0.0) * 100.0,
                t["flake_score"].as_f64().unwrap_or(0.0),
                t["run_count"],
            );
        }
    }

    // ------------------------------------------------------------------
    // 5. GET /api/resonance/flaky
    // ------------------------------------------------------------------
    section("GET /api/resonance/flaky");

    let (status, json) = get_json(&app, "/api/resonance/flaky").await;
    println!("HTTP {status}\n");
    println!(
        "total_analyzed: {}  min_runs: {}",
        json["total_analyzed"], json["min_runs"]
    );
    println!("\nFlaky tests (sorted by stability ↑):");
    if let Some(tests) = json["flaky_tests"].as_array() {
        if tests.is_empty() {
            println!("  (none above min_runs threshold)");
        }
        for t in tests {
            println!(
                "  {:12} stability={:.0}%  flake_score={:.3}  runs={}  is_flaky={}",
                format!(
                    "{}/{}",
                    t["suite"].as_str().unwrap_or("?"),
                    t["name"].as_str().unwrap_or("?")
                ),
                t["stability_score"].as_f64().unwrap_or(0.0) * 100.0,
                t["flake_score"].as_f64().unwrap_or(0.0),
                t["run_count"],
                t["is_flaky"],
            );
        }
    }

    println!();
}
