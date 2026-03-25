// utoipa::path proc-macro expands to code that calls Option::unwrap() internally.
// We allow the lint at file scope to avoid spurious errors on generated code.
#![allow(clippy::disallowed_methods)]

use crate::alerting::{AlertManager, AlertSeverity};
use crate::{ApiResponse, AppState};
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use liminalqa_core::{
    baseline::NoiseFilter,
    entities::*,
    resonance::{stability_score, FlakeDetector, SignalImportance},
    triage::{TriageEngine, TriageVerdict},
    types::*,
};
use liminalqa_db::LiminalDB;
use serde::Serialize;
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// Response DTOs
// ---------------------------------------------------------------------------

#[derive(Serialize)]
pub struct FlakyTestEntry {
    pub name: String,
    pub suite: String,
    /// Pass rate 0.0–1.0 (1.0 = always passes).
    pub stability_score: f64,
    /// Transition-based flakiness score 0.0–1.0 (higher = more oscillating).
    pub flake_score: f64,
    pub run_count: usize,
    pub is_flaky: bool,
}

#[derive(Serialize)]
pub struct FlakyTestsResponse {
    pub flaky_tests: Vec<FlakyTestEntry>,
    pub total_analyzed: usize,
    /// Minimum run count required before a test is included.
    pub min_runs: usize,
}

#[derive(Serialize)]
pub struct RankedSignal {
    pub signal_id: String,
    pub signal_type: String,
    pub latency_ms: Option<u64>,
    pub importance: f64,
    pub timestamp: String,
}

#[derive(Serialize)]
pub struct SignalsResponse {
    pub run_id: String,
    pub signals: Vec<RankedSignal>,
    /// Latency values after Z-score noise filtering (|z| > 3.0 removed).
    pub filtered_latencies_ms: Vec<f64>,
}

#[derive(Serialize)]
pub struct TriageEntry {
    pub name: String,
    pub suite: String,
    pub verdict: String,
    pub stability_score: f64,
    pub flake_score: f64,
    pub run_count: usize,
}

#[derive(Serialize)]
pub struct TriageResponse {
    pub tests: Vec<TriageEntry>,
    pub total_analyzed: usize,
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

/// GET /api/resonance/flaky
///
/// Returns all known tests with a flakiness score and stability score,
/// sorted from least stable to most stable.
/// Only tests with at least 5 recorded runs are included.
#[utoipa::path(
    get,
    path = "/api/resonance/flaky",
    responses(
        (status = 200, description = "Ranked list of flaky tests", body = serde_json::Value),
        (status = 401, description = "Unauthorized", body = crate::ApiResponse),
        (status = 429, description = "Rate limit exceeded", body = crate::ApiResponse),
        (status = 500, description = "Internal server error", body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_flaky_tests(State(state): State<AppState>) -> impl IntoResponse {
    const LOOKBACK: usize = 20;
    const MIN_RUNS: usize = 5;

    let db = &state.db;

    let known = match db.list_known_tests() {
        Ok(v) => v,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!(ApiResponse::error(format!(
                    "Failed to list known tests: {}",
                    e
                )))),
            )
                .into_response();
        }
    };

    let total_analyzed = known.len();
    let detector = FlakeDetector::default();
    let mut entries: Vec<FlakyTestEntry> = Vec::new();

    for (name, suite) in &known {
        let history = match db.get_test_history(name, suite, LOOKBACK) {
            Ok(h) => h,
            Err(e) => {
                warn!("History fetch failed for {}/{}: {}", name, suite, e);
                continue;
            }
        };

        if history.len() < MIN_RUNS {
            continue;
        }

        let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();
        let stab = stability_score(&statuses);
        let flake = detector.calculate_score(&statuses);
        let is_flaky = detector.is_flaky(&statuses) || stab < 0.9;

        entries.push(FlakyTestEntry {
            name: name.clone(),
            suite: suite.clone(),
            stability_score: stab,
            flake_score: flake,
            run_count: history.len(),
            is_flaky,
        });
    }

    // Sort: least stable first
    entries.sort_by(|a, b| {
        a.stability_score
            .partial_cmp(&b.stability_score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let resp = FlakyTestsResponse {
        flaky_tests: entries,
        total_analyzed,
        min_runs: MIN_RUNS,
    };

    (StatusCode::OK, Json(serde_json::json!(resp))).into_response()
}

/// GET /api/resonance/signals/:run_id
///
/// Returns all signals for a run, ranked by importance score
/// (type weight × latency factor).
#[utoipa::path(
    get,
    path = "/api/resonance/signals/{run_id}",
    params(
        ("run_id" = String, Path, description = "ULID of the run")
    ),
    responses(
        (status = 200, description = "Signals ranked by importance", body = serde_json::Value),
        (status = 400, description = "Invalid run_id", body = crate::ApiResponse),
        (status = 401, description = "Unauthorized", body = crate::ApiResponse),
        (status = 500, description = "Internal server error", body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_signals_by_run(
    State(state): State<AppState>,
    Path(run_id_str): Path<String>,
) -> impl IntoResponse {
    let run_id = match EntityId::from_string(&run_id_str) {
        Ok(id) => id,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!(ApiResponse::error("Invalid run_id"))),
            )
                .into_response();
        }
    };

    let mut signals = match state.db.get_signals_by_run(run_id) {
        Ok(s) => s,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!(ApiResponse::error(format!(
                    "Failed to fetch signals: {}",
                    e
                )))),
            )
                .into_response();
        }
    };

    // Score and sort descending
    signals.sort_by(|a, b| {
        SignalImportance::compute(b)
            .partial_cmp(&SignalImportance::compute(a))
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    // Collect raw latencies and filter noise before ranking
    let raw_latencies: Vec<f64> = signals
        .iter()
        .filter_map(|s| s.latency_ms.map(|v| v as f64))
        .collect();
    let filtered_latencies_ms = NoiseFilter::filter_zscore(&raw_latencies, 3.0);

    let ranked: Vec<RankedSignal> = signals
        .iter()
        .map(|s| RankedSignal {
            signal_id: s.id.to_string(),
            signal_type: format!("{:?}", s.signal_type),
            latency_ms: s.latency_ms,
            importance: SignalImportance::compute(s),
            timestamp: s.timestamp.to_rfc3339(),
        })
        .collect();

    let resp = SignalsResponse {
        run_id: run_id_str,
        signals: ranked,
        filtered_latencies_ms,
    };

    (StatusCode::OK, Json(serde_json::json!(resp))).into_response()
}

/// GET /api/triage
///
/// Classifies every known test as `stable`, `flake`, `new_bug`, or
/// `known_issue` based on recent run history.
/// Only tests with at least 3 runs are included.
#[utoipa::path(
    get,
    path = "/api/triage",
    responses(
        (status = 200, description = "Triage verdicts for all known tests", body = serde_json::Value),
        (status = 401, description = "Unauthorized", body = crate::ApiResponse),
        (status = 429, description = "Rate limit exceeded", body = crate::ApiResponse),
        (status = 500, description = "Internal server error", body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_triage(State(state): State<AppState>) -> impl IntoResponse {
    const LOOKBACK: usize = 20;

    let db = &state.db;
    let known = match db.list_known_tests() {
        Ok(v) => v,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!(ApiResponse::error(format!(
                    "Failed to list known tests: {}",
                    e
                )))),
            )
                .into_response();
        }
    };

    let total_analyzed = known.len();
    let engine = TriageEngine::default();
    let detector = FlakeDetector::default();
    let mut tests: Vec<TriageEntry> = Vec::new();

    for (name, suite) in &known {
        let history = match db.get_test_history(name, suite, LOOKBACK) {
            Ok(h) => h,
            Err(e) => {
                warn!("History fetch failed for {}/{}: {}", name, suite, e);
                continue;
            }
        };

        let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();
        let verdict = engine.classify(&statuses);
        let stab = stability_score(&statuses);
        let flake = detector.calculate_score(&statuses);

        tests.push(TriageEntry {
            name: name.clone(),
            suite: suite.clone(),
            verdict: verdict.to_string(),
            stability_score: stab,
            flake_score: flake,
            run_count: history.len(),
        });
    }

    // Sort: new_bug and known_issue first, then flake, then stable
    tests.sort_by_key(|e| match e.verdict.as_str() {
        "new_bug" => 0,
        "known_issue" => 1,
        "flake" => 2,
        _ => 3,
    });

    let resp = TriageResponse {
        tests,
        total_analyzed,
    };

    (StatusCode::OK, Json(serde_json::json!(resp))).into_response()
}

// ---------------------------------------------------------------------------
// Ingest-time helper
// ---------------------------------------------------------------------------

/// Called after each test ingest to update flakiness tracking and fire alerts.
pub fn check_and_record_flakiness(db: &LiminalDB, test: &Test, alerts: &AlertManager) {
    let history = match db.get_test_history(&test.name, &test.suite, 20) {
        Ok(h) => h,
        Err(e) => {
            warn!("Failed to get history for test {}: {}", test.name, e);
            return;
        }
    };

    let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();
    let detector = FlakeDetector::default();
    let flake_score = detector.calculate_score(&statuses);
    let stab = stability_score(&statuses);

    // Auto-triage: classify and fire alerts for new regressions / flakes
    let triage_engine = TriageEngine::default();
    let verdict = triage_engine.classify(&statuses);
    match verdict {
        TriageVerdict::NewBug => alerts.notify(
            AlertSeverity::Critical,
            &format!("New regression: {}/{}", test.suite, test.name),
            &format!(
                "Test was stable (stability={:.0}%) but last {} runs all failed.",
                stab * 100.0,
                3,
            ),
        ),
        TriageVerdict::Flake => alerts.notify(
            AlertSeverity::Warning,
            &format!("Flaky test: {}/{}", test.suite, test.name),
            &format!(
                "Oscillation detected — flake_score={:.2}, stability={:.0}%.",
                flake_score,
                stab * 100.0
            ),
        ),
        _ => {}
    }

    if detector.is_flaky(&statuses) || (history.len() >= 5 && stab < 0.9) {
        info!(
            "Test '{}' ({}) is flaky — stability={:.2} flake_score={:.2}",
            test.name, test.suite, stab, flake_score
        );

        let resonance = Resonance {
            id: EntityId::new(),
            pattern: ResonancePattern {
                pattern_id: EntityId::new(),
                description: format!(
                    "Flaky test: {} / {} (stability={:.0}%, flake_score={:.2})",
                    test.name,
                    test.suite,
                    stab * 100.0,
                    flake_score
                ),
                score: flake_score,
                occurrences: history.len() as u32,
                first_seen: history
                    .last()
                    .map(|t| t.started_at)
                    .unwrap_or_else(chrono::Utc::now),
                last_seen: test.started_at,
            },
            affected_tests: vec![test.id],
            root_cause: None,
            created_at: liminalqa_core::temporal::BiTemporalTime::now(),
        };

        if let Err(e) = db.put_resonance(&resonance) {
            warn!("Failed to store resonance: {}", e);
        }
    }
}
