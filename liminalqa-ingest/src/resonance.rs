// utoipa::path proc-macro expands to code that calls Option::unwrap() internally.
// We allow the lint at file scope to avoid spurious errors on generated code.
#![allow(clippy::disallowed_methods)]

use crate::alerting::{AlertManager, AlertSeverity};
use crate::{ApiResponse, AppState};
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use liminalqa_core::{
    baseline::NoiseFilter,
    causality::CausalityWalker,
    context::SignalContext,
    entities::*,
    resonance::{stability_score, FlakeDetector, SignalImportance},
    retry::RetryPolicy,
    triage::{TriageEngine, TriageVerdict},
    types::*,
};
use liminalqa_db::LiminalDB;
use serde::Deserialize;
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

/// Query parameters for `GET /api/resonance/signals/:run_id`.
#[derive(Debug, Deserialize, Default)]
pub struct SignalsQuery {
    /// Environment label: `prod`, `staging`, or `dev` (default: `dev`).
    pub env: Option<String>,
    /// CPU utilisation 0–100 at observation time (default: Normal load).
    pub cpu: Option<f64>,
}

#[derive(Serialize)]
pub struct RankedSignal {
    pub signal_id: String,
    pub signal_type: String,
    pub latency_ms: Option<u64>,
    /// Raw importance before context adjustment.
    pub base_importance: f64,
    /// Importance after applying env / time-window / load-level multipliers.
    pub adjusted_importance: f64,
    /// Combined context multiplier that was applied.
    pub context_multiplier: f64,
    pub timestamp: String,
}

#[derive(Serialize)]
pub struct SignalsResponse {
    pub run_id: String,
    /// Environment used for context scoring.
    pub environment: String,
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
    Query(params): Query<SignalsQuery>,
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

    let signals = match state.db.get_signals_by_run(run_id) {
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

    // Resolve environment label for the response
    let env_label = params.env.as_deref().unwrap_or("dev").to_string();

    // Collect raw latencies and filter noise
    let raw_latencies: Vec<f64> = signals
        .iter()
        .filter_map(|s| s.latency_ms.map(|v| v as f64))
        .collect();
    let filtered_latencies_ms = NoiseFilter::filter_zscore(&raw_latencies, 3.0);

    // Score, apply context, and sort descending by adjusted_importance
    let mut ranked: Vec<RankedSignal> = signals
        .iter()
        .map(|s| {
            let ctx =
                SignalContext::from_signal_meta(&s.timestamp, params.env.as_deref(), params.cpu);
            let base = SignalImportance::compute(s);
            let adjusted = ctx.apply(base);
            RankedSignal {
                signal_id: s.id.to_string(),
                signal_type: format!("{:?}", s.signal_type),
                latency_ms: s.latency_ms,
                base_importance: base,
                adjusted_importance: adjusted,
                context_multiplier: ctx.multiplier(),
                timestamp: s.timestamp.to_rfc3339(),
            }
        })
        .collect();

    ranked.sort_by(|a, b| {
        b.adjusted_importance
            .partial_cmp(&a.adjusted_importance)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let resp = SignalsResponse {
        run_id: run_id_str,
        environment: env_label,
        signals: ranked,
        filtered_latencies_ms,
    };

    (StatusCode::OK, Json(serde_json::json!(resp))).into_response()
}

/// GET /api/causality/:run_id/:signal_id
///
/// Returns the multi-hop causal chain starting from `signal_id` within the
/// context of `run_id`. Optional `?depth=N` (default 4) limits walk depth.
#[utoipa::path(
    get,
    path = "/api/causality/{run_id}/{signal_id}",
    params(
        ("run_id"    = String, Path, description = "ULID of the run"),
        ("signal_id" = String, Path, description = "ULID of the root signal"),
        ("depth"     = Option<usize>, Query, description = "Max hops (default 4)"),
    ),
    responses(
        (status = 200, description = "Causal chain from root signal", body = serde_json::Value),
        (status = 400, description = "Invalid ID",                    body = crate::ApiResponse),
        (status = 404, description = "Signal not found in run",       body = crate::ApiResponse),
        (status = 401, description = "Unauthorized",                  body = crate::ApiResponse),
        (status = 500, description = "Internal server error",         body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_causality_chain(
    State(state): State<AppState>,
    Path((run_id_str, signal_id_str)): Path<(String, String)>,
    Query(params): Query<CausalityQuery>,
) -> impl IntoResponse {
    let run_id = match EntityId::from_string(&run_id_str) {
        Ok(id) => id,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!(ApiResponse::error("Invalid run_id"))),
            )
                .into_response()
        }
    };
    let signal_id = match EntityId::from_string(&signal_id_str) {
        Ok(id) => id,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!(ApiResponse::error("Invalid signal_id"))),
            )
                .into_response()
        }
    };

    let signals = match state.db.get_signals_by_run(run_id) {
        Ok(s) => s,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!(ApiResponse::error(format!(
                    "Failed to fetch signals: {}",
                    e
                )))),
            )
                .into_response()
        }
    };

    let max_depth = params.depth.unwrap_or(4).clamp(1, 8);
    let walker = CausalityWalker {
        max_depth,
        ..Default::default()
    };

    match walker.walk(signal_id, &signals) {
        Some(chain) => (StatusCode::OK, Json(serde_json::json!(chain))).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!(ApiResponse::error(
                "Signal not found in this run"
            ))),
        )
            .into_response(),
    }
}

/// Query parameters for `GET /api/causality/:run_id/:signal_id`.
#[derive(Debug, Deserialize, Default)]
pub struct CausalityQuery {
    /// Maximum hops to follow (1–8, default 4).
    pub depth: Option<usize>,
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

// ---------------------------------------------------------------------------
// EMA Baseline endpoint
// ---------------------------------------------------------------------------

/// Response from `GET /api/baseline/:suite/:test_name`.
#[derive(Serialize)]
pub struct BaselineResponse {
    pub name: String,
    pub suite: String,
    pub ema_mean_ms: f64,
    pub ema_stddev_ms: f64,
    /// Confidence 0.0–1.0 (≥0.95 after ~3×period samples).
    pub confidence: f64,
    pub is_warmed_up: bool,
    pub sample_count: u64,
}

/// GET /api/baseline/:suite/:test_name
///
/// Returns the current EMA baseline statistics (mean, stddev, confidence)
/// for the given test.  The baseline is updated automatically on every
/// test ingest and does not require explicit population.
#[utoipa::path(
    get,
    path = "/api/baseline/{suite}/{test_name}",
    params(
        ("suite" = String, Path, description = "Test suite name"),
        ("test_name" = String, Path, description = "Test name"),
    ),
    responses(
        (status = 200, description = "EMA baseline statistics", body = serde_json::Value),
        (status = 404, description = "No baseline data yet",     body = crate::ApiResponse),
        (status = 401, description = "Unauthorized",             body = crate::ApiResponse),
        (status = 500, description = "Internal server error",    body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_baseline(
    State(state): State<AppState>,
    Path((suite, name)): Path<(String, String)>,
) -> impl IntoResponse {
    match state.db.get_ema_baseline(&name, &suite) {
        Ok(Some(baseline)) => {
            let (mean, stddev, confidence) = baseline.stats();
            let resp = BaselineResponse {
                name,
                suite,
                ema_mean_ms: mean,
                ema_stddev_ms: stddev,
                confidence,
                is_warmed_up: baseline.is_warmed_up(),
                sample_count: baseline.sample_count(),
            };
            (StatusCode::OK, Json(serde_json::json!(resp))).into_response()
        }
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!(ApiResponse::error(
                "No baseline data yet for this test"
            ))),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!(ApiResponse::error(format!(
                "Database error: {}",
                e
            )))),
        )
            .into_response(),
    }
}

// ---------------------------------------------------------------------------
// Timeout advice endpoint
// ---------------------------------------------------------------------------

/// Response from `GET /api/timeout-advice/:suite/:test_name`.
#[derive(Serialize)]
pub struct TimeoutAdvice {
    pub name: String,
    pub suite: String,
    /// Suggested timeout in milliseconds (`EMA_mean + sigma_factor × EMA_stddev`).
    /// `null` when the baseline has not warmed up yet.
    pub suggested_timeout_ms: Option<u64>,
    /// The sigma factor used (default 3.0).
    pub sigma_factor: f64,
    pub ema_mean_ms: f64,
    pub ema_stddev_ms: f64,
    pub confidence: f64,
    pub is_warmed_up: bool,
}

/// Query parameters for `GET /api/timeout-advice`.
#[derive(Debug, Deserialize, Default)]
pub struct TimeoutQuery {
    /// Sigma multiplier for the timeout formula (default 3.0).
    pub sigma: Option<f64>,
}

/// GET /api/timeout-advice/:suite/:test_name
///
/// Returns an adaptive timeout recommendation derived from the EMA baseline.
/// Formula: `timeout_ms = EMA_mean + sigma × EMA_stddev` (default sigma=3).
/// Returns `null` for `suggested_timeout_ms` when the baseline is not yet
/// warmed up (fewer than `period/2` samples).
#[utoipa::path(
    get,
    path = "/api/timeout-advice/{suite}/{test_name}",
    params(
        ("suite"     = String, Path, description = "Test suite name"),
        ("test_name" = String, Path, description = "Test name"),
        ("sigma"     = Option<f64>, Query, description = "Sigma multiplier (default 3.0)"),
    ),
    responses(
        (status = 200, description = "Adaptive timeout advice",      body = serde_json::Value),
        (status = 404, description = "No baseline data yet",         body = crate::ApiResponse),
        (status = 401, description = "Unauthorized",                 body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_timeout_advice(
    State(state): State<AppState>,
    Path((suite, name)): Path<(String, String)>,
    Query(params): Query<TimeoutQuery>,
) -> impl IntoResponse {
    let sigma = params.sigma.unwrap_or(3.0).clamp(1.0, 6.0);
    match state.db.get_ema_baseline(&name, &suite) {
        Ok(Some(baseline)) => {
            let (mean, stddev, confidence) = baseline.stats();
            let resp = TimeoutAdvice {
                name,
                suite,
                suggested_timeout_ms: baseline.suggested_timeout_ms(sigma),
                sigma_factor: sigma,
                ema_mean_ms: mean,
                ema_stddev_ms: stddev,
                confidence,
                is_warmed_up: baseline.is_warmed_up(),
            };
            (StatusCode::OK, Json(serde_json::json!(resp))).into_response()
        }
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!(ApiResponse::error(
                "No baseline data yet for this test"
            ))),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!(ApiResponse::error(format!(
                "Database error: {}",
                e
            )))),
        )
            .into_response(),
    }
}

// ---------------------------------------------------------------------------
// Smart test-selection / run-plan endpoint
// ---------------------------------------------------------------------------

/// Decision for a single test in a run plan.
#[derive(Serialize)]
pub struct TestRunDecision {
    pub name: String,
    pub suite: String,
    pub action: RunAction,
    pub reason: String,
    /// Stability score 0.0–1.0 (higher = more stable).
    pub stability_score: f64,
    /// Triage verdict for context.
    pub verdict: String,
    pub run_count: usize,
}

#[derive(Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RunAction {
    /// Always run — new test, no history yet.
    AlwaysRun,
    /// Run — flaky or broken, must be watched.
    Run,
    /// Recommended to skip — rock-solid for many runs.
    Skip,
}

/// Response from `GET /api/run-plan/:suite`.
#[derive(Serialize)]
pub struct RunPlan {
    pub suite: String,
    pub total_tests: usize,
    pub recommended_to_run: usize,
    pub recommended_to_skip: usize,
    pub decisions: Vec<TestRunDecision>,
}

/// Query parameters for `GET /api/run-plan/:suite`.
#[derive(Debug, Deserialize, Default)]
pub struct RunPlanQuery {
    /// Stability threshold above which a test is recommended for skipping
    /// (default 0.97 — the test must have passed at least 97 % of recent runs).
    pub skip_threshold: Option<f64>,
    /// Minimum number of historical runs required before a test can be skipped
    /// (default 10).
    pub min_runs: Option<usize>,
}

/// GET /api/run-plan/:suite
///
/// Returns a smart run plan for the given suite.  Tests that have been rock-solid
/// for many runs are flagged as `skip`; flaky / broken / new tests are flagged
/// as `run` or `always_run`.
///
/// This allows CI pipelines to reduce their test budget on a given commit
/// without sacrificing confidence.
#[utoipa::path(
    get,
    path = "/api/run-plan/{suite}",
    params(
        ("suite"           = String, Path,  description = "Suite name"),
        ("skip_threshold"  = Option<f64>,   Query, description = "Stability threshold for skip (default 0.97)"),
        ("min_runs"        = Option<usize>, Query, description = "Minimum historical runs before skipping (default 10)"),
    ),
    responses(
        (status = 200, description = "Run plan for the suite",    body = serde_json::Value),
        (status = 401, description = "Unauthorized",              body = crate::ApiResponse),
        (status = 500, description = "Internal server error",     body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_run_plan(
    State(state): State<AppState>,
    Path(suite): Path<String>,
    Query(params): Query<RunPlanQuery>,
) -> impl IntoResponse {
    let skip_threshold = params.skip_threshold.unwrap_or(0.97).clamp(0.5, 1.0);
    let min_runs = params.min_runs.unwrap_or(10);
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

    let engine = TriageEngine::default();
    let mut decisions: Vec<TestRunDecision> = Vec::new();

    for (name, test_suite) in &known {
        if test_suite != &suite {
            continue;
        }
        let history = match db.get_test_history(name, test_suite, LOOKBACK) {
            Ok(h) => h,
            Err(_) => continue,
        };

        if history.is_empty() {
            // Brand-new test — always run
            decisions.push(TestRunDecision {
                name: name.clone(),
                suite: test_suite.clone(),
                action: RunAction::AlwaysRun,
                reason: "No history — new test".into(),
                stability_score: 1.0,
                verdict: "unknown".into(),
                run_count: 0,
            });
            continue;
        }

        let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();
        let stab = stability_score(&statuses);
        let verdict = engine.classify(&statuses);
        let run_count = history.len();

        // Recommend a retry policy based on verdict — used only for the
        // `reason` string, not directly enforced here.
        let policy = RetryPolicy::from_triage(&verdict, stab);

        let (action, reason) = match verdict {
            TriageVerdict::NewBug | TriageVerdict::KnownIssue => (
                RunAction::Run,
                format!(
                    "{} — must run to track regression (policy: {})",
                    verdict,
                    policy.describe()
                ),
            ),
            TriageVerdict::Flake => (
                RunAction::Run,
                format!(
                    "Flaky test (stability={:.0}%) — run to gather signal (policy: {})",
                    stab * 100.0,
                    policy.describe()
                ),
            ),
            TriageVerdict::Stable => {
                if run_count >= min_runs && stab >= skip_threshold {
                    (
                        RunAction::Skip,
                        format!(
                            "Rock-solid: {:.0}% pass rate over {} runs — safe to skip",
                            stab * 100.0,
                            run_count
                        ),
                    )
                } else {
                    (
                        RunAction::Run,
                        format!(
                            "Stable but only {} run(s) — need {} before skipping",
                            run_count, min_runs
                        ),
                    )
                }
            }
        };

        decisions.push(TestRunDecision {
            name: name.clone(),
            suite: test_suite.clone(),
            action,
            reason,
            stability_score: stab,
            verdict: verdict.to_string(),
            run_count,
        });
    }

    // Sort: always_run first, then run, then skip; within same action sort by stability asc
    decisions.sort_by(|a, b| {
        let priority = |d: &TestRunDecision| match d.action {
            RunAction::AlwaysRun => 0,
            RunAction::Run => 1,
            RunAction::Skip => 2,
        };
        priority(a)
            .cmp(&priority(b))
            .then_with(|| a.stability_score.partial_cmp(&b.stability_score).unwrap())
    });

    let recommended_to_skip = decisions
        .iter()
        .filter(|d| d.action == RunAction::Skip)
        .count();
    let recommended_to_run = decisions.len() - recommended_to_skip;

    let plan = RunPlan {
        suite,
        total_tests: decisions.len(),
        recommended_to_run,
        recommended_to_skip,
        decisions,
    };

    (StatusCode::OK, Json(serde_json::json!(plan))).into_response()
}

// ---------------------------------------------------------------------------
// Duration trend endpoint
// ---------------------------------------------------------------------------

/// GET /api/trend/:suite/:test_name
///
/// Returns linear-regression stats over the test's duration history.
/// `slope_ms_per_run > 0` means the test is getting slower; `< 0` means faster.
/// `r_squared` indicates how linear the trend is (1.0 = perfect line).
#[utoipa::path(
    get,
    path = "/api/trend/{suite}/{test_name}",
    params(
        ("suite"     = String, Path, description = "Test suite name"),
        ("test_name" = String, Path, description = "Test name"),
    ),
    responses(
        (status = 200, description = "Duration trend regression stats", body = serde_json::Value),
        (status = 404, description = "No trend data yet (< 3 samples)",  body = crate::ApiResponse),
        (status = 401, description = "Unauthorized",                      body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_trend(
    State(state): State<AppState>,
    Path((suite, name)): Path<(String, String)>,
) -> impl IntoResponse {
    match state.db.get_duration_trend(&name, &suite) {
        Ok(Some(trend)) => match trend.regression() {
            Some(stats) => {
                let direction = if stats.slope_ms_per_run > 0.5 {
                    "degrading"
                } else if stats.slope_ms_per_run < -0.5 {
                    "improving"
                } else {
                    "stable"
                };
                (
                    StatusCode::OK,
                    Json(serde_json::json!({
                        "name": name,
                        "suite": suite,
                        "slope_ms_per_run": stats.slope_ms_per_run,
                        "intercept_ms": stats.intercept_ms,
                        "r_squared": stats.r_squared,
                        "sample_count": stats.sample_count,
                        "direction": direction,
                    })),
                )
                    .into_response()
            }
            None => (
                StatusCode::NOT_FOUND,
                Json(serde_json::json!(ApiResponse::error(
                    "Not enough data yet (need ≥ 3 samples)"
                ))),
            )
                .into_response(),
        },
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!(ApiResponse::error(
                "No trend data yet for this test"
            ))),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!(ApiResponse::error(format!(
                "Database error: {}",
                e
            )))),
        )
            .into_response(),
    }
}

// ---------------------------------------------------------------------------
// Flake risk / predictive flake probability endpoint
// ---------------------------------------------------------------------------

/// GET /api/flake-risk/:suite/:test_name
///
/// Returns an estimated probability (0.0–1.0) that the test will flake on
/// the next run, derived from:
/// - Recent stability score (pass rate)
/// - Transition-based flake score (oscillation)
/// - Triage verdict weight
/// - Duration trend (degrading tests flake more)
#[utoipa::path(
    get,
    path = "/api/flake-risk/{suite}/{test_name}",
    params(
        ("suite"     = String, Path, description = "Test suite name"),
        ("test_name" = String, Path, description = "Test name"),
    ),
    responses(
        (status = 200, description = "Flake risk assessment",           body = serde_json::Value),
        (status = 404, description = "No history yet (< 3 runs)",       body = crate::ApiResponse),
        (status = 401, description = "Unauthorized",                    body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Analysis"
)]
pub async fn get_flake_risk(
    State(state): State<AppState>,
    Path((suite, name)): Path<(String, String)>,
) -> impl IntoResponse {
    const LOOKBACK: usize = 20;

    let history = match state.db.get_test_history(&name, &suite, LOOKBACK) {
        Ok(h) => h,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!(ApiResponse::error(format!(
                    "Database error: {}",
                    e
                )))),
            )
                .into_response();
        }
    };

    if history.len() < 3 {
        return (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!(ApiResponse::error(
                "Not enough history yet (need ≥ 3 runs)"
            ))),
        )
            .into_response();
    }

    let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();
    let stability = stability_score(&statuses);
    let detector = FlakeDetector::default();
    let flake_score = detector.calculate_score(&statuses);
    let engine = TriageEngine::default();
    let verdict = engine.classify(&statuses);

    // Verdict weight: new_bug and known_issue lean toward 0 (not flaky, just broken)
    let verdict_factor = match verdict {
        TriageVerdict::Flake => 1.0,
        TriageVerdict::Stable => 0.0,
        TriageVerdict::NewBug | TriageVerdict::KnownIssue => 0.2,
    };

    // Trend factor: degrading duration → slightly higher flake risk
    let trend_factor = match state.db.get_duration_trend(&name, &suite) {
        Ok(Some(trend)) => match trend.regression() {
            Some(stats) if stats.slope_ms_per_run > 5.0 => 0.1,
            _ => 0.0,
        },
        _ => 0.0,
    };

    // Composite: weighted blend
    //   40% from instability (1 - stability)
    //   40% from oscillation (flake_score)
    //   20% from verdict
    //   +trend bonus (up to +10%)
    let raw = 0.40 * (1.0 - stability) + 0.40 * flake_score + 0.20 * verdict_factor + trend_factor;
    let flake_probability = raw.clamp(0.0, 1.0);

    let risk_label = if flake_probability >= 0.7 {
        "high"
    } else if flake_probability >= 0.35 {
        "medium"
    } else {
        "low"
    };

    let policy = RetryPolicy::from_triage(&verdict, stability);

    (
        StatusCode::OK,
        Json(serde_json::json!({
            "name": name,
            "suite": suite,
            "flake_probability": flake_probability,
            "risk_label": risk_label,
            "stability_score": stability,
            "flake_score": flake_score,
            "verdict": verdict.to_string(),
            "suggested_retry_policy": policy.describe(),
            "run_count": history.len(),
        })),
    )
        .into_response()
}
