//! Prometheus metrics for LiminalQA Ingest

use prometheus::{
    register_histogram_vec, register_int_counter_vec, register_int_gauge_vec,
    HistogramVec, IntCounterVec, IntGaugeVec,
};
use once_cell::sync::Lazy;

// Request metrics
pub static HTTP_REQUESTS_TOTAL: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "liminalqa_http_requests_total",
        "Total HTTP requests",
        &["method", "endpoint", "status"]
    )
    .unwrap()
});

pub static HTTP_REQUEST_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "liminalqa_http_request_duration_seconds",
        "HTTP request duration in seconds",
        &["method", "endpoint"]
    )
    .unwrap()
});

// Ingestion metrics
pub static ENTITIES_INGESTED: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "liminalqa_entities_ingested_total",
        "Total entities ingested",
        &["entity_type"]
    )
    .unwrap()
});

pub static BATCH_SIZE: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "liminalqa_batch_size",
        "Size of batch ingestion requests",
        &["entity_type"]
    )
    .unwrap()
});

// Database metrics
pub static DB_OPERATIONS: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "liminalqa_db_operations_total",
        "Total database operations",
        &["operation", "status"]
    )
    .unwrap()
});

pub static DB_OPERATION_DURATION: Lazy<HistogramVec> = Lazy::new(|| {
    register_histogram_vec!(
        "liminalqa_db_operation_duration_seconds",
        "Database operation duration",
        &["operation"]
    )
    .unwrap()
});

// Active connections
pub static ACTIVE_CONNECTIONS: Lazy<IntGaugeVec> = Lazy::new(|| {
    register_int_gauge_vec!(
        "liminalqa_active_connections",
        "Number of active connections",
        &["type"]
    )
    .unwrap()
});
