use anyhow::Result;
use axum::{
    body::{to_bytes, Body},
    http::{header, Request, StatusCode},
    Router,
};
use liminalqa_core::metrics::MetricsRegistry;
use liminalqa_db::LiminalDB;
use liminalqa_ingest::{alerting::AlertManager, app, AppState, RateLimiter};
use serde_json::Value;
use std::sync::Arc;
use tempfile::TempDir;
use tower::util::ServiceExt;

const TEST_TOKEN: &str = "docs-test-token";
const MAX_ASSET_BYTES: usize = 8 * 1024 * 1024;

fn authenticated_app() -> Result<(Router, TempDir)> {
    let db_dir = tempfile::tempdir()?;
    let state = AppState {
        db: Arc::new(LiminalDB::open(db_dir.path())?),
        auth_token: Some(TEST_TOKEN.to_string()),
        metrics: Arc::new(MetricsRegistry::new()),
        rate_limiter: Arc::new(RateLimiter::new(10_000)),
        alerts: AlertManager::from_env(),
    };
    Ok((app(state), db_dir))
}

fn get(path: &str) -> Result<Request<Body>> {
    Ok(Request::builder().uri(path).body(Body::empty())?)
}

#[tokio::test]
async fn docs_redirect_and_embedded_assets_remain_public() -> Result<()> {
    let (app, _db_dir) = authenticated_app()?;
    let response = app.clone().oneshot(get("/docs")?).await?;
    assert_eq!(response.status(), StatusCode::SEE_OTHER);
    assert_eq!(response.headers()[header::LOCATION], "/docs/");

    for (path, content_type, expected_text) in [
        ("/docs/", "text/html", "swagger-ui-bundle.js"),
        ("/docs/swagger-ui.css", "text/css", ".swagger-ui"),
        (
            "/docs/swagger-ui-bundle.js",
            "text/javascript",
            "SwaggerUIBundle",
        ),
        (
            "/docs/swagger-initializer.js",
            "text/javascript",
            "/api-docs/openapi.json",
        ),
    ] {
        let response = app.clone().oneshot(get(path)?).await?;
        assert_eq!(response.status(), StatusCode::OK, "{path}");
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            content_type,
            "{path}"
        );
        assert!(
            !response.headers().contains_key(header::CONTENT_ENCODING),
            "Uncompressed assets must not be marked as gzip: {path}"
        );
        let bytes = to_bytes(response.into_body(), MAX_ASSET_BYTES).await?;
        let body = std::str::from_utf8(&bytes)?;
        assert!(body.contains(expected_text), "{path}");
    }
    Ok(())
}

#[tokio::test]
async fn missing_or_traversal_assets_return_not_found() -> Result<()> {
    let (app, _db_dir) = authenticated_app()?;
    for path in [
        "/docs/does-not-exist.js",
        "/docs/../Cargo.toml",
        "/docs/%2e%2e%2fCargo.toml",
    ] {
        let response = app.clone().oneshot(get(path)?).await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND, "{path}");
    }
    Ok(())
}

#[tokio::test]
async fn openapi_preserves_existing_contract_and_bearer_security() -> Result<()> {
    let (app, _db_dir) = authenticated_app()?;
    let response = app.oneshot(get("/api-docs/openapi.json")?).await?;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()[header::CONTENT_TYPE], "application/json");

    let bytes = to_bytes(response.into_body(), MAX_ASSET_BYTES).await?;
    let spec: Value = serde_json::from_slice(&bytes)?;
    assert_eq!(spec["openapi"], "3.0.3");
    assert_eq!(spec["info"]["title"], "LiminalQA Ingest API");
    assert!(spec["components"]["schemas"]["RunDto"].is_object());
    assert!(spec["components"]["schemas"]["ApiResponse"].is_object());
    assert_eq!(
        spec["components"]["securitySchemes"]["bearer_token"]["type"],
        "http"
    );
    assert_eq!(
        spec["components"]["securitySchemes"]["bearer_token"]["scheme"],
        "bearer"
    );

    for (path, method) in [
        ("/ingest/run", "post"),
        ("/query", "post"),
        ("/api/decision/{suite}/{test_name}", "get"),
        ("/api/decision/suite/{suite}", "get"),
    ] {
        let operation = &spec["paths"][path][method];
        assert!(operation.is_object(), "{method} {path}");
        assert_eq!(
            operation["security"][0]["bearer_token"],
            serde_json::json!([]),
            "{method} {path}"
        );
    }
    Ok(())
}

#[tokio::test]
async fn serving_public_docs_does_not_bypass_protected_api_auth() -> Result<()> {
    let (app, _db_dir) = authenticated_app()?;
    let path = "/api/decision/test-suite/missing-test";
    let response = app.clone().oneshot(get(path)?).await?;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);

    let request = Request::builder()
        .uri(path)
        .header(header::AUTHORIZATION, "Bearer incorrect-token")
        .body(Body::empty())?;
    let response = app.clone().oneshot(request).await?;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);

    let request = Request::builder()
        .uri(path)
        .header(header::AUTHORIZATION, format!("Bearer {TEST_TOKEN}"))
        .body(Body::empty())?;
    let response = app.oneshot(request).await?;
    // Authentication succeeds; the real handler reports that the test has no history.
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    Ok(())
}
