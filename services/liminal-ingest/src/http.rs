//! HTTP handlers for ingest API

use crate::models::{ApiResponse, ArtifactsDto, RunDto, SignalsDto, TestsDto};
use crate::store::Store;
use actix_web::{get, post, web, HttpResponse, Responder};
use tracing::{error, info};

/// Health check endpoint
#[get("/health")]
pub async fn health() -> impl Responder {
    HttpResponse::Ok().json(serde_json::json!({
        "ok": true,
        "service": "liminal-ingest",
        "version": env!("CARGO_PKG_VERSION")
    }))
}

/// Ingest a test run
#[post("/ingest/run")]
pub async fn ingest_run(
    dto: web::Json<RunDto>,
    store: web::Data<Store>,
) -> impl Responder {
    info!("Ingesting run: {}", dto.run_id);

    match store.put_run(&dto).await {
        Ok(_) => {
            info!("Run ingested successfully: {}", dto.run_id);
            HttpResponse::Ok().json(ApiResponse::ok())
        }
        Err(e) => {
            error!("Failed to ingest run {}: {}", dto.run_id, e);
            HttpResponse::InternalServerError().json(ApiResponse::error(format!(
                "Failed to ingest run: {}",
                e
            )))
        }
    }
}

/// Ingest test results
#[post("/ingest/tests")]
pub async fn ingest_tests(
    dto: web::Json<TestsDto>,
    store: web::Data<Store>,
) -> impl Responder {
    info!("Ingesting {} tests for run: {}", dto.tests.len(), dto.run_id);

    match store.put_tests(dto.run_id, &dto.tests, dto.valid_from).await {
        Ok(_) => {
            info!("Tests ingested successfully for run: {}", dto.run_id);
            HttpResponse::Ok().json(ApiResponse::ok())
        }
        Err(e) => {
            error!("Failed to ingest tests for run {}: {}", dto.run_id, e);
            HttpResponse::InternalServerError().json(ApiResponse::error(format!(
                "Failed to ingest tests: {}",
                e
            )))
        }
    }
}

/// Ingest signals
#[post("/ingest/signals")]
pub async fn ingest_signals(
    dto: web::Json<SignalsDto>,
    store: web::Data<Store>,
) -> impl Responder {
    info!("Ingesting {} signals for run: {}", dto.signals.len(), dto.run_id);

    match store.put_signals(dto.run_id, &dto.signals).await {
        Ok(_) => {
            info!("Signals ingested successfully for run: {}", dto.run_id);
            HttpResponse::Ok().json(ApiResponse::ok())
        }
        Err(e) => {
            error!("Failed to ingest signals for run {}: {}", dto.run_id, e);
            HttpResponse::InternalServerError().json(ApiResponse::error(format!(
                "Failed to ingest signals: {}",
                e
            )))
        }
    }
}

/// Ingest artifacts
#[post("/ingest/artifacts")]
pub async fn ingest_artifacts(
    dto: web::Json<ArtifactsDto>,
    store: web::Data<Store>,
) -> impl Responder {
    info!("Ingesting {} artifacts for run: {}", dto.artifacts.len(), dto.run_id);

    match store.put_artifacts(dto.run_id, &dto.artifacts).await {
        Ok(_) => {
            info!("Artifacts ingested successfully for run: {}", dto.run_id);
            HttpResponse::Ok().json(ApiResponse::ok())
        }
        Err(e) => {
            error!("Failed to ingest artifacts for run {}: {}", dto.run_id, e);
            HttpResponse::InternalServerError().json(ApiResponse::error(format!(
                "Failed to ingest artifacts: {}",
                e
            )))
        }
    }
}
