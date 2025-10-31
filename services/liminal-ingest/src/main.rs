//! Liminal Ingest Service - REST API for test data ingestion

mod auth;
mod http;
mod models;
mod store;

use actix_web::{middleware, App, HttpServer};
use anyhow::Result;
use std::env;
use store::Store;
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

#[actix_web::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(EnvFilter::from_default_env())
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    info!("Starting Liminal Ingest Service");

    // Read configuration
    let pg_url = env::var("LIMINAL_PG_URL")
        .unwrap_or_else(|_| "postgres://liminal:liminal@localhost:5432/liminal".to_string());
    let api_token = env::var("LIMINAL_API_TOKEN").unwrap_or_else(|_| "devtoken".to_string());
    let bind_addr = env::var("LIMINAL_BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:8088".to_string());

    info!("Connecting to database: {}", pg_url);

    // Initialize store
    let store = Store::new(&pg_url).await?;
    info!("Database connection pool created");

    // Start HTTP server
    info!("Starting HTTP server on {}", bind_addr);

    HttpServer::new(move || {
        App::new()
            .app_data(actix_web::web::Data::new(store.clone()))
            .app_data(actix_web::web::Data::new(api_token.clone()))
            .wrap(middleware::Logger::default())
            .wrap(tracing_actix_web::TracingLogger::default())
            .service(http::health)
            .service(http::ingest_run)
            .service(http::ingest_tests)
            .service(http::ingest_signals)
            .service(http::ingest_artifacts)
    })
    .bind(bind_addr)?
    .run()
    .await?;

    Ok(())
}
