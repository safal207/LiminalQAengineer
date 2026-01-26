// use liminalqa_db::LiminalDB;
// use liminalqa_core::entities::Test;

pub fn check_and_record_flakiness(_db: &(), _test: &()) {
    // TODO: Re-implement with PostgresStorage (Async)
}

pub async fn get_flaky_tests() -> impl axum::response::IntoResponse {
    axum::Json(serde_json::json!([]))
}
