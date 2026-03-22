//! LiminalQA Ingest Library

pub mod baseline;
pub mod handlers;
pub mod resonance;

use axum::{
    extract::{Request, State},
    http::{header, StatusCode},
    middleware::{self, Next},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use liminalqa_core::metrics::SharedMetrics;
use liminalqa_db::LiminalDB;
use serde::{Deserialize, Serialize};
use std::fmt;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

use crate::handlers::*;
use crate::resonance::get_flaky_tests;

/// Simple global rate limiter (sliding window, per-second)
pub struct RateLimiter {
    count: AtomicU64,
    window_start: AtomicU64,
    max_per_second: u64,
}

impl RateLimiter {
    pub fn new(max_per_second: u64) -> Self {
        Self {
            count: AtomicU64::new(0),
            window_start: AtomicU64::new(0),
            max_per_second,
        }
    }

    pub fn check(&self) -> bool {
        let now_secs = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let prev = self.window_start.load(Ordering::Relaxed);
        if now_secs > prev {
            self.window_start.store(now_secs, Ordering::Relaxed);
            self.count.store(1, Ordering::Relaxed);
            return true;
        }

        self.count.fetch_add(1, Ordering::Relaxed) < self.max_per_second
    }
}

#[derive(Clone)]
pub struct AppState {
    pub db: Arc<LiminalDB>,
    pub auth_token: Option<String>,
    pub metrics: SharedMetrics,
    pub rate_limiter: Arc<RateLimiter>,
}

/// Debug impl masks the auth token to prevent accidental secret leaks in logs
impl fmt::Debug for AppState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("AppState")
            .field(
                "auth_token",
                &self.auth_token.as_ref().map(|_| "[REDACTED]"),
            )
            .finish_non_exhaustive()
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ApiResponse {
    pub ok: bool,
    pub message: String,
}

impl ApiResponse {
    pub fn ok(message: impl Into<String>) -> Self {
        Self {
            ok: true,
            message: message.into(),
        }
    }

    pub fn error(message: impl Into<String>) -> Self {
        Self {
            ok: false,
            message: message.into(),
        }
    }
}

pub fn app(state: AppState) -> Router {
    Router::new()
        .route("/ingest/run", post(ingest_run))
        .route("/ingest/tests", post(ingest_tests))
        .route("/ingest/signals", post(ingest_signals))
        .route("/ingest/artifacts", post(ingest_artifacts))
        .route("/ingest/batch", post(ingest_batch))
        .route("/query", post(query_handler))
        .route("/api/resonance/flaky", get(get_flaky_tests))
        .route("/metrics", get(metrics_handler))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limit_middleware,
        ))
        .route("/health", get(health_check))
        .layer(tower_http::cors::CorsLayer::permissive())
        .with_state(state)
}

async fn health_check() -> impl IntoResponse {
    #[derive(Serialize)]
    struct HealthCheck {
        status: String,
        service: String,
        version: String,
    }

    let body = HealthCheck {
        status: "ok".to_string(),
        service: "liminalqa-ingest".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    };
    Json(body)
}

async fn metrics_handler(State(state): State<AppState>) -> impl IntoResponse {
    let body = state.metrics.export();
    (
        [(
            header::CONTENT_TYPE,
            "application/openmetrics-text; version=1.0.0; charset=utf-8",
        )],
        body,
    )
}

async fn rate_limit_middleware(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<impl IntoResponse, (StatusCode, Json<ApiResponse>)> {
    if !state.rate_limiter.check() {
        return Err((
            StatusCode::TOO_MANY_REQUESTS,
            Json(ApiResponse::error("Rate limit exceeded. Please retry later.")),
        ));
    }
    Ok(next.run(req).await)
}

/// Constant-time string comparison to prevent timing attacks on bearer tokens
fn constant_time_eq(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }
    a.bytes()
        .zip(b.bytes())
        .fold(0u8, |acc, (x, y)| acc | (x ^ y))
        == 0
}

async fn auth_middleware(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<impl IntoResponse, (StatusCode, Json<ApiResponse>)> {
    if let Some(ref expected_token) = state.auth_token {
        let auth_header = req
            .headers()
            .get(header::AUTHORIZATION)
            .and_then(|h| h.to_str().ok());

        let authenticated = match auth_header {
            Some(auth_str) if auth_str.starts_with("Bearer ") => {
                let token = &auth_str[7..];
                constant_time_eq(token, expected_token)
            }
            _ => false,
        };

        if !authenticated {
            return Err((
                StatusCode::UNAUTHORIZED,
                Json(ApiResponse::error("Unauthorized: Invalid or missing token")),
            ));
        }
    }

    Ok(next.run(req).await)
}
