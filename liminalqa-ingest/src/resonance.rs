use crate::{ApiResponse, AppState};
use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use liminalqa_core::{entities::*, resonance::FlakeDetector, types::*};
use liminalqa_db::LiminalDB;
use tracing::{info, warn};

/// GET /api/resonance/flaky
pub async fn get_flaky_tests(State(state): State<AppState>) -> impl IntoResponse {
    let db = &state.db;

    // Scan all Resonance entities
    let flaky_ids = match db.get_entities_by_type(EntityType::Resonance) {
        Ok(ids) => ids,
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiResponse::error(format!(
                    "Failed to scan resonance entities: {}",
                    e
                ))),
            )
                .into_response();
        }
    };

    let mut flaky_tests = Vec::new();
    for id in flaky_ids {
        if let Ok(Some(resonance)) = db.get_entity::<Resonance>(id) {
            flaky_tests.push(resonance);
        }
    }

    (StatusCode::OK, Json(flaky_tests)).into_response()
}

/// Helper to check if a test is flaky and record it
pub fn check_and_record_flakiness(db: &LiminalDB, test: &Test) {
    // 1. Get history (last 20 runs)
    let history = match db.get_test_history(&test.name, &test.suite, 20) {
        Ok(h) => h,
        Err(e) => {
            warn!("Failed to get history for test {}: {}", test.name, e);
            return;
        }
    };

    // 2. Extract statuses
    let statuses: Vec<TestStatus> = history.iter().map(|t| t.status).collect();

    // 3. Detect
    let detector = FlakeDetector::default();
    let score = detector.calculate_score(&statuses);

    if detector.is_flaky(&statuses) {
        info!(
            "Test {} identified as flaky! Score: {:.2}",
            test.name, score
        );

        let resonance = Resonance {
            id: EntityId::new(),
            pattern: ResonancePattern {
                pattern_id: EntityId::new(),
                description: format!("Flaky test detected: {} (Score: {:.2})", test.name, score),
                score,
                occurrences: 1,
                first_seen: chrono::Utc::now(),
                last_seen: chrono::Utc::now(),
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
