// utoipa proc-macro calls Option::unwrap() internally.
#![allow(clippy::disallowed_methods)]

//! HTTP handlers for the agent-facing decision layer.
//!
//! Two endpoints:
//! - `GET /api/decision/:suite/:test_name` — single-test decision packet
//! - `GET /api/decision/suite/:suite`       — suite / PR-level judgment

use crate::{ApiResponse, AppState};
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use liminalqa_core::{
    decision::{DecisionEngine, SuiteDecision, TestDecision, TestSignals},
    resonance::{stability_score, FlakeDetector},
    triage::TriageEngine,
    types::TestStatus,
};
use tracing::warn;

const LOOKBACK: usize = 20;

// ---------------------------------------------------------------------------
// Shared helper: build a TestDecision from DB state
// ---------------------------------------------------------------------------

/// Fetch all signals from the database and assemble a `TestDecision`.
/// Returns `None` if there is not enough history (< 3 runs).
fn build_test_decision(
    state: &AppState,
    name: &str,
    suite: &str,
) -> Result<Option<TestDecision>, String> {
    let history = state
        .db
        .get_test_history(name, suite, LOOKBACK)
        .map_err(|e| format!("DB error fetching history: {e}"))?;

    if history.len() < 3 {
        return Ok(None);
    }

    let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();
    let stability = stability_score(&statuses);
    let detector = FlakeDetector::default();
    let flake_score = detector.calculate_score(&statuses);
    let engine = TriageEngine::default();
    let verdict = engine.classify(&statuses);

    // Composite flake probability (mirrors /api/flake-risk formula)
    let trend_bonus = match state.db.get_duration_trend(name, suite) {
        Ok(Some(trend)) => match trend.regression() {
            Some(s) if s.slope_ms_per_run > 5.0 => 0.1,
            _ => 0.0,
        },
        _ => 0.0,
    };
    let flake_probability =
        (0.40 * (1.0 - stability) + 0.40 * flake_score + 0.20 * 0.0 + trend_bonus).clamp(0.0, 1.0);

    let trend = state
        .db
        .get_duration_trend(name, suite)
        .ok()
        .flatten()
        .and_then(|t| t.regression());

    let baseline = state.db.get_ema_baseline(name, suite).ok().flatten();

    let decision = DecisionEngine::evaluate_test(TestSignals {
        name,
        suite,
        verdict,
        stability,
        flake_probability,
        flake_score,
        trend: trend.as_ref(),
        baseline: baseline.as_ref(),
        run_count: history.len(),
    });

    Ok(Some(decision))
}

// ---------------------------------------------------------------------------
// GET /api/decision/:suite/:test_name
// ---------------------------------------------------------------------------

/// GET /api/decision/:suite/:test_name
///
/// Returns a complete decision packet for one test — optimised for direct
/// consumption by AI agents, GitHub bots, and CLI tools.
///
/// The `recommended_action` and `merge_policy` fields use a closed vocabulary:
///
/// | `recommended_action`  | Meaning                                |
/// |-----------------------|----------------------------------------|
/// | `run`                 | Execute normally                       |
/// | `retry_immediately`   | Likely transient — retry once          |
/// | `retry_with_backoff`  | High-risk flake — exponential backoff  |
/// | `investigate`         | Consistent failure — escalate          |
/// | `monitor_trend`       | Stable but degrading — watch closely   |
/// | `skip`                | Rock-solid — safe to omit              |
/// | `block_and_alert`     | New regression — halt pipeline         |
/// | `observe_only`        | Not enough history yet                 |
///
/// | `merge_policy`        | Meaning                                |
/// |-----------------------|----------------------------------------|
/// | `allow`               | Merge is safe                          |
/// | `allow_with_warning`  | Merge with annotation                  |
/// | `block_soft`          | Human approval required                |
/// | `block`               | Hard block — new regression            |
/// | `unknown`             | Insufficient data                      |
#[utoipa::path(
    get,
    path = "/api/decision/{suite}/{test_name}",
    params(
        ("suite"     = String, Path, description = "Test suite name"),
        ("test_name" = String, Path, description = "Test name"),
    ),
    responses(
        (status = 200, description = "Agent-facing decision packet", body = serde_json::Value),
        (status = 404, description = "Not enough run history (< 3 runs)", body = crate::ApiResponse),
        (status = 401, description = "Unauthorized",                      body = crate::ApiResponse),
        (status = 500, description = "Internal server error",             body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Decision"
)]
pub async fn get_test_decision(
    State(state): State<AppState>,
    Path((suite, name)): Path<(String, String)>,
) -> impl IntoResponse {
    match build_test_decision(&state, &name, &suite) {
        Ok(Some(decision)) => (StatusCode::OK, Json(serde_json::json!(decision))).into_response(),
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!(ApiResponse::error(
                "Not enough run history yet (need ≥ 3 runs)"
            ))),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!(ApiResponse::error(e))),
        )
            .into_response(),
    }
}

// ---------------------------------------------------------------------------
// GET /api/decision/suite/:suite
// ---------------------------------------------------------------------------

/// GET /api/decision/suite/:suite
///
/// Aggregates all tests in the suite into a single PR-level / suite-level
/// judgment.
///
/// The `merge_policy` field reflects the **worst** policy across all tests:
/// a single new regression produces `"block"` even if all other tests pass.
///
/// `action_items` lists only tests that require agent or human attention —
/// stable skip-worthy tests are omitted to reduce noise.
///
/// ## Example use by a PR bot
/// ```text
/// if decision["merge_policy"] == "block":
///     post_comment(decision["block_reason"])
///     set_status("failure")
/// elif decision["merge_policy"] == "allow_with_warning":
///     post_comment(format_warnings(decision["action_items"]))
///     set_status("success")
/// else:
///     set_status("success")
/// ```
#[utoipa::path(
    get,
    path = "/api/decision/suite/{suite}",
    params(
        ("suite" = String, Path, description = "Suite name"),
    ),
    responses(
        (status = 200, description = "Suite-level / PR-level decision",  body = serde_json::Value),
        (status = 401, description = "Unauthorized",                      body = crate::ApiResponse),
        (status = 500, description = "Internal server error",             body = crate::ApiResponse),
    ),
    security(("bearer_token" = [])),
    tag = "Decision"
)]
pub async fn get_suite_decision(
    State(state): State<AppState>,
    Path(suite): Path<String>,
) -> impl IntoResponse {
    let known = match state.db.list_known_tests() {
        Ok(v) => v,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!(ApiResponse::error(format!(
                    "Failed to list known tests: {e}"
                )))),
            )
                .into_response();
        }
    };

    let mut decisions: Vec<TestDecision> = Vec::new();

    for (name, test_suite) in &known {
        if test_suite != &suite {
            continue;
        }
        match build_test_decision(&state, name, test_suite) {
            Ok(Some(d)) => decisions.push(d),
            Ok(None) => {} // not enough history — skip from aggregate
            Err(e) => {
                warn!("Decision failed for {}/{}: {}", test_suite, name, e);
            }
        }
    }

    let suite_decision: SuiteDecision = DecisionEngine::evaluate_suite(&suite, &decisions);
    (StatusCode::OK, Json(serde_json::json!(suite_decision))).into_response()
}
