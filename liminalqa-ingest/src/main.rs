//! LiminalQA Ingest Server — REST API for test run data ingestion

use anyhow::Result;
use axum::{
    extract::State,
    http::StatusCode,
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

mod handlers;

use handlers::*;

#[derive(Clone)]
struct AppState {
    db: Arc<LiminalDB>,
}

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

    let state = AppState { db: Arc::new(db) };

    // Build router
    let app = Router::new()
        .route("/health", get(health_check))
        .route("/ingest/run", post(ingest_run))
        .route("/ingest/tests", post(ingest_tests))
        .route("/ingest/signals", post(ingest_signals))
        .route("/ingest/artifacts", post(ingest_artifacts))
        .route("/query", post(query_handler))
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

#[derive(Debug, Serialize, Deserialize)]
struct ApiResponse {
    success: bool,
    message: String,
}

impl ApiResponse {
    fn ok(message: impl Into<String>) -> Self {
        Self {
            success: true,
            message: message.into(),
        }
    }

    fn error(message: impl Into<String>) -> Self {
        Self {
            success: false,
            message: message.into(),
        }
    }
}
