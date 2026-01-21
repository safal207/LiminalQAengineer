//! LiminalQA Ingest Library

pub mod handlers;

use axum::{
    extract::{Request, State},
    http::{header, StatusCode},
    middleware::{self, Next},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use liminalqa_db::LiminalDB;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tower_http::cors::CorsLayer;

use crate::handlers::*;

#[derive(Clone)]
pub struct AppState {
    pub db: Arc<LiminalDB>,
    pub auth_token: Option<String>,
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
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .route("/health", get(health_check))
        .layer(CorsLayer::permissive())
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
                token == expected_token
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
