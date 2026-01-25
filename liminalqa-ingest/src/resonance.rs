use crate::{ApiResponse, AppState};
use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::Test, resonance::FlakeDetector, types::*};
use liminalqa_db::{models::ResonanceScore, PostgresStorage};
use tracing::{info, warn};

/// GET /api/resonance/flaky
pub async fn get_flaky_tests(State(state): State<AppState>) -> impl IntoResponse {
    let db = &state.db;

    // Get resonance scores
    match db.get_resonance_scores().await {
        Ok(scores) => (StatusCode::OK, Json(scores)).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiResponse::error(format!(
                "Failed to get resonance scores: {}",
                e
            ))),
        )
            .into_response(),
    }
}

/// Helper to check if a test is flaky and record it
pub async fn check_and_record_flakiness(db: &PostgresStorage, test: &Test) {
    // 1. Get history (last 20 runs)
    let history = match db.get_test_history(&test.name, &test.suite, 20).await {
        Ok(h) => h,
        Err(e) => {
            warn!("Failed to get history for test {}: {}", test.name, e);
            return;
        }
    };

    // 2. Extract statuses
    let statuses: Vec<TestStatus> = history
        .iter()
        .map(|t| match t.status.as_str() {
            "pass" | "passed" | "success" => TestStatus::Pass,
            "fail" | "failed" | "error" => TestStatus::Fail,
            "xfail" => TestStatus::XFail,
            "flake" | "flaky" => TestStatus::Flake,
            "timeout" => TestStatus::Timeout,
            _ => TestStatus::Skip,
        })
        .collect();

    // 3. Detect
    let detector = FlakeDetector::default();
    let score = detector.calculate_score(&statuses);

    if detector.is_flaky(&statuses) {
        info!(
            "Test {} identified as flaky! Score: {:.2}",
            test.name, score
        );

        let resonance_score = ResonanceScore {
            test_name: test.name.clone(),
            suite: test.suite.clone(),
            score,
            correlated_tests: None, // TODO: Implement correlation analysis
            last_calculated: chrono::Utc::now(),
        };

        if let Err(e) = db.upsert_resonance_score(&resonance_score).await {
            warn!("Failed to store resonance score: {}", e);
        }
    }
}
