//! LiminalQA Ingest Server — REST API for test run data ingestion

use anyhow::Result;
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
use std::{net::SocketAddr, path::PathBuf, sync::Arc};
use tower_http::{cors::CorsLayer, trace::TraceLayer};
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

use liminalqa_ingest::handlers::*;
use liminalqa_ingest::{ApiResponse, AppState};

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .with_target(false)
        .compact()
        .finish();
    tracing::subscriber::set_global_default(subscriber)?;

    info!("Starting LiminalQA Ingest Server");

    // Open database
    let db_path = std::env::var("LIMINAL_DB_PATH")
        .unwrap_or_else(|_| "./data/liminaldb".to_string());
    info!("Opening database at: {}", db_path);
    let db = LiminalDB::open(PathBuf::from(db_path))?;

    let auth_token = std::env::var("LIMINAL_AUTH_TOKEN").ok();
    if auth_token.is_none() {
        tracing::error!(
            "LIMINAL_AUTH_TOKEN not set! Authentication is DISABLED. \
            This is a SECURITY RISK in production. Set LIMINAL_AUTH_TOKEN \
            environment variable to enable authentication."
        );
        // In production, consider making this a hard error:
        // return Err(anyhow::anyhow!("LIMINAL_AUTH_TOKEN must be set"));
    }

    let state = AppState {
        db: Arc::new(db),
        auth_token,
    };

    // Build router
    let app = Router::new()
        .route("/ingest/run", post(ingest_run))
        .route("/ingest/tests", post(ingest_tests))
        .route("/ingest/signals", post(ingest_signals))
        .route("/ingest/artifacts", post(ingest_artifacts))
        .route("/query", post(query_handler))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .route("/health", get(health_check))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    info!("Listening on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

async fn health_check() -> impl IntoResponse {
    Json(serde_json::json!({
        "status": "ok",
        "service": "liminalqa-ingest",
        "version": env!("CARGO_PKG_VERSION")
    }))
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

