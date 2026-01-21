//! LiminalQA Ingest Server — REST API for test run data ingestion

use anyhow::Result;
use liminalqa_db::LiminalDB;
use std::{net::SocketAddr, path::PathBuf, sync::Arc};
use tower_http::trace::TraceLayer;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

use liminalqa_ingest::AppState;

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
    let db_path =
        std::env::var("LIMINAL_DB_PATH").unwrap_or_else(|_| "./data/liminaldb".to_string());
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
    let app = liminalqa_ingest::app(state).layer(TraceLayer::new_for_http());

    // Start server
    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    info!("Listening on http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app)
        .await
        .map_err(|e| anyhow::anyhow!(e))?;

    #[allow(clippy::disallowed_methods)]
    Ok(())
}
