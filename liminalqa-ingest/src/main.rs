//! LiminalQA Ingest Server — REST API for test run data ingestion

use anyhow::Result;
use liminalqa_db::PostgresStorage;
use std::{net::SocketAddr, sync::Arc};
use tower_http::trace::TraceLayer;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

use liminalqa_core::metrics::MetricsRegistry;
use liminalqa_grpc::{IngestServiceServer, MyIngestService};
use liminalqa_ingest::AppState;
use tonic::transport::Server;

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
    let database_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgres://liminal:liminal@localhost:5432/liminalqa".to_string());

    info!("Connecting to database at {}", database_url);

    // Initialize Postgres Storage (runs migrations)
    let db = PostgresStorage::new(&database_url).await?;

    let auth_token = std::env::var("LIMINAL_AUTH_TOKEN").ok();
    if auth_token.is_none() {
        tracing::error!(
            "LIMINAL_AUTH_TOKEN not set! Authentication is DISABLED. \
            This is a SECURITY RISK in production. Set LIMINAL_AUTH_TOKEN \
            environment variable to enable authentication."
        );
    }

    // Initialize metrics
    let metrics = Arc::new(MetricsRegistry::new());

    let state = AppState {
        db: db.clone(),
        auth_token,
        metrics,
    };

    // Build REST Router
    let app = liminalqa_ingest::app(state).layer(TraceLayer::new_for_http());

    // Start servers
    let rest_addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    let grpc_addr = "[::0]:50051".parse().unwrap();

    info!("REST Listening on http://{}", rest_addr);
    info!("gRPC Listening on {}", grpc_addr);

    let rest_server = async {
        let listener = tokio::net::TcpListener::bind(rest_addr).await?;
        axum::serve(listener, app)
            .await
            .map_err(|e| anyhow::anyhow!(e))
    };

    let grpc_service = MyIngestService::new(db.clone());
    let grpc_server = Server::builder()
        .add_service(IngestServiceServer::new(grpc_service))
        .serve(grpc_addr);

    tokio::select! {
        res = rest_server => {
            if let Err(e) = res {
                tracing::error!("REST server failed: {}", e);
            }
        },
        res = grpc_server => {
            if let Err(e) = res {
                tracing::error!("gRPC server failed: {}", e);
            }
        }
    }

    #[allow(clippy::disallowed_methods)]
    Ok(())
}
