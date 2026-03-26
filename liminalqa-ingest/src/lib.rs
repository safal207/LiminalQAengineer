//! LiminalQA Ingest Library

pub mod alerting;
pub mod baseline;
pub mod decision_handler;
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
use utoipa::{openapi::security, Modify, OpenApi, ToSchema};
use utoipa_swagger_ui::SwaggerUi;

use crate::alerting::AlertManager;
use crate::decision_handler::{get_suite_decision, get_test_decision};
use crate::handlers::*;
use crate::resonance::{
    get_baseline, get_causality_chain, get_flake_risk, get_flaky_tests, get_run_plan,
    get_signals_by_run, get_triage, get_timeout_advice, get_trend,
};

// ---------------------------------------------------------------------------
// Rate limiter
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct AppState {
    pub db: Arc<LiminalDB>,
    pub auth_token: Option<String>,
    pub metrics: SharedMetrics,
    pub rate_limiter: Arc<RateLimiter>,
    pub alerts: AlertManager,
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

// ---------------------------------------------------------------------------
// API response type
// ---------------------------------------------------------------------------

/// Generic API response envelope
#[derive(Debug, Serialize, Deserialize, ToSchema)]
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

// ---------------------------------------------------------------------------
// OpenAPI spec
// ---------------------------------------------------------------------------

struct BearerSecurityAddon;

impl Modify for BearerSecurityAddon {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        let components = openapi.components.get_or_insert_with(Default::default);
        components.add_security_scheme(
            "bearer_token",
            security::SecurityScheme::Http(
                security::HttpBuilder::new()
                    .scheme(security::HttpAuthScheme::Bearer)
                    .bearer_format("opaque token")
                    .build(),
            ),
        );
    }
}

#[derive(OpenApi)]
#[openapi(
    info(
        title = "LiminalQA Ingest API",
        description = "REST API for ingesting test runs, results, signals and artifacts into LiminalQA. \
                       All protected endpoints require a Bearer token set via `LIMINAL_AUTH_TOKEN`.",
        version = "0.1.0",
        contact(
            name = "LiminalQA",
            url = "https://github.com/safal207/LiminalQAengineer"
        ),
        license(name = "MIT"),
    ),
    paths(
        handlers::ingest_run,
        handlers::ingest_tests,
        handlers::ingest_signals,
        handlers::ingest_artifacts,
        handlers::ingest_batch,
        handlers::query_handler,
        resonance::get_flaky_tests,
        resonance::get_signals_by_run,
        resonance::get_triage,
        resonance::get_causality_chain,
        resonance::get_baseline,
        resonance::get_timeout_advice,
        resonance::get_run_plan,
        resonance::get_trend,
        resonance::get_flake_risk,
        decision_handler::get_test_decision,
        decision_handler::get_suite_decision,
    ),
    components(schemas(
        ApiResponse,
        RunDto,
        TestsDto,
        TestDtoItem,
        SignalsDto,
        SignalDtoItem,
        ArtifactsDto,
        ArtifactDtoItem,
        BatchIngestDto,
        BatchIngestResponse,
        BatchCounts,
    )),
    modifiers(&BearerSecurityAddon),
    tags(
        (name = "Ingest", description = "Ingest test data into LIMINAL-DB"),
        (name = "Query",  description = "Bi-temporal data queries"),
        (name = "Analysis", description = "Flakiness and baseline drift analysis"),
    )
)]
pub struct ApiDoc;

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

pub fn app(state: AppState) -> Router {
    Router::new()
        // Protected routes (behind auth + rate-limit middleware)
        .route("/ingest/run", post(ingest_run))
        .route("/ingest/tests", post(ingest_tests))
        .route("/ingest/signals", post(ingest_signals))
        .route("/ingest/artifacts", post(ingest_artifacts))
        .route("/ingest/batch", post(ingest_batch))
        .route("/query", post(query_handler))
        .route("/api/resonance/flaky", get(get_flaky_tests))
        .route("/api/resonance/signals/:run_id", get(get_signals_by_run))
        .route("/api/triage", get(get_triage))
        .route(
            "/api/causality/:run_id/:signal_id",
            get(get_causality_chain),
        )
        .route("/api/baseline/:suite/:test_name", get(get_baseline))
        .route(
            "/api/timeout-advice/:suite/:test_name",
            get(get_timeout_advice),
        )
        .route("/api/run-plan/:suite", get(get_run_plan))
        .route("/api/trend/:suite/:test_name", get(get_trend))
        .route("/api/flake-risk/:suite/:test_name", get(get_flake_risk))
        // Decision layer — agent-facing endpoints
        .route(
            "/api/decision/suite/:suite",
            get(get_suite_decision),
        )
        .route(
            "/api/decision/:suite/:test_name",
            get(get_test_decision),
        )
        .route("/metrics", get(metrics_handler))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limit_middleware,
        ))
        // Public routes (no auth required)
        .route("/health", get(health_check))
        .merge(SwaggerUi::new("/docs").url("/api-docs/openapi.json", ApiDoc::openapi()))
        .layer(tower_http::cors::CorsLayer::permissive())
        .with_state(state)
}

// ---------------------------------------------------------------------------
// Handlers (public)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------

async fn rate_limit_middleware(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<impl IntoResponse, (StatusCode, Json<ApiResponse>)> {
    if !state.rate_limiter.check() {
        return Err((
            StatusCode::TOO_MANY_REQUESTS,
            Json(ApiResponse::error(
                "Rate limit exceeded. Please retry later.",
            )),
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
