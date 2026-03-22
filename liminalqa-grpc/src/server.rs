use crate::liminalqa::v1::{
    ingest_service_server::IngestService, IngestRunRequest, IngestRunResponse, IngestTestsRequest,
    IngestTestsResponse, Signal, SignalAck,
};
use chrono::TimeZone;
use liminalqa_core::{
    entities::{Signal as SignalEntity, Test},
    temporal::BiTemporalTime,
    types::{EntityId, SignalType, TestStatus},
};
use liminalqa_db::LiminalDB;
use std::{collections::HashMap, pin::Pin, sync::Arc};
use tokio_stream::{Stream, StreamExt};
use tonic::{Request, Response, Status};

pub struct MyIngestService {
    db: Arc<LiminalDB>,
}

impl MyIngestService {
    pub fn new(db: Arc<LiminalDB>) -> Self {
        Self { db }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn parse_ulid(s: &str, field: &str) -> Result<EntityId, Status> {
    EntityId::from_string(s)
        .map_err(|e| Status::invalid_argument(format!("Invalid {}: {}", field, e)))
}

fn ms_to_datetime(ms: i64, field: &str) -> Result<chrono::DateTime<chrono::Utc>, Status> {
    chrono::Utc
        .timestamp_millis_opt(ms)
        .single()
        .ok_or_else(|| Status::invalid_argument(format!("Invalid timestamp for {}", field)))
}

fn map_test_status(s: &str) -> TestStatus {
    match s.to_lowercase().as_str() {
        "pass" | "passed" | "success" => TestStatus::Pass,
        "fail" | "failed" | "error" => TestStatus::Fail,
        "xfail" => TestStatus::XFail,
        "flake" | "flaky" => TestStatus::Flake,
        "timeout" => TestStatus::Timeout,
        _ => TestStatus::Skip,
    }
}

fn map_signal_type(s: &str) -> SignalType {
    match s.to_lowercase().as_str() {
        "ui" => SignalType::UI,
        "api" => SignalType::API,
        "websocket" | "ws" => SignalType::WebSocket,
        "grpc" => SignalType::GRPC,
        "database" | "db" => SignalType::Database,
        "network" => SignalType::Network,
        _ => SignalType::System,
    }
}

// ---------------------------------------------------------------------------
// Service implementation
// ---------------------------------------------------------------------------

#[tonic::async_trait]
impl IngestService for MyIngestService {
    // ── IngestRun ─────────────────────────────────────────────────────────

    async fn ingest_run(
        &self,
        request: Request<IngestRunRequest>,
    ) -> Result<Response<IngestRunResponse>, Status> {
        let req = request.into_inner();

        let run_id = liminalqa_core::types::new_entity_id();
        let build_id = parse_ulid(&req.build_id, "build_id")?;

        let env: HashMap<String, String> = serde_json::from_str(&req.env)
            .map_err(|e| Status::invalid_argument(format!("Invalid env JSON: {}", e)))?;

        let started_at = ms_to_datetime(req.started_at, "started_at")?;
        let ended_at = req
            .ended_at
            .map(|ts| ms_to_datetime(ts, "ended_at"))
            .transpose()?;

        let run = liminalqa_core::entities::Run {
            id: run_id,
            build_id,
            plan_name: req.plan_name,
            env,
            started_at,
            ended_at,
            runner_version: req.runner_version,
            liminal_os_version: req.liminal_os_version,
            created_at: BiTemporalTime::now(),
        };

        self.db
            .put_run(&run)
            .map_err(|e| Status::internal(format!("Failed to store run: {}", e)))?;

        Ok(Response::new(IngestRunResponse {
            run_id: run_id.to_string(),
        }))
    }

    // ── IngestTests ───────────────────────────────────────────────────────

    async fn ingest_tests(
        &self,
        request: Request<IngestTestsRequest>,
    ) -> Result<Response<IngestTestsResponse>, Status> {
        let req = request.into_inner();
        let run_id = parse_ulid(&req.run_id, "run_id")?;

        let mut processed = 0i32;
        let mut failed = 0i32;
        let mut failed_ids: Vec<String> = Vec::new();

        for proto_test in &req.tests {
            let test_id = if let Some(ref id_str) = proto_test.id {
                if id_str.is_empty() {
                    EntityId::new()
                } else {
                    match parse_ulid(id_str, "test.id") {
                        Ok(id) => id,
                        Err(_) => EntityId::new(),
                    }
                }
            } else {
                EntityId::new()
            };

            let started_at = ms_to_datetime(proto_test.started_at, "test.started_at")?;
            let completed_at = ms_to_datetime(proto_test.completed_at, "test.completed_at")?;

            let error = proto_test.error_message.as_ref().map(|msg| {
                liminalqa_core::types::TestError {
                    error_type: "TestError".to_string(),
                    message: msg.clone(),
                    stack_trace: None,
                    source_location: None,
                }
            });

            let test = Test {
                id: test_id,
                run_id,
                name: proto_test.name.clone(),
                suite: proto_test.suite.clone(),
                guidance: proto_test.guidance.clone(),
                status: map_test_status(&proto_test.status),
                duration_ms: proto_test.duration_ms,
                error,
                started_at,
                completed_at,
                created_at: BiTemporalTime::now(),
            };

            match self.db.put_test(&test) {
                Ok(_) => processed += 1,
                Err(e) => {
                    failed += 1;
                    failed_ids.push(format!("{}: {}", test_id, e));
                }
            }
        }

        Ok(Response::new(IngestTestsResponse {
            processed_count: processed,
            failed_count: failed,
            failed_ids,
        }))
    }

    // ── StreamSignals ─────────────────────────────────────────────────────

    type StreamSignalsStream = Pin<Box<dyn Stream<Item = Result<SignalAck, Status>> + Send>>;

    async fn stream_signals(
        &self,
        request: Request<tonic::Streaming<Signal>>,
    ) -> Result<Response<Self::StreamSignalsStream>, Status> {
        let mut stream = request.into_inner();
        let db = self.db.clone();

        let output = async_stream::try_stream! {
            while let Some(signal_result) = stream.next().await {
                let proto_sig = signal_result?;

                let signal_id = EntityId::new();

                // Parse run_id and test_id
                let run_id = match parse_ulid(&proto_sig.run_id, "run_id") {
                    Ok(id) => id,
                    Err(e) => {
                        yield SignalAck {
                            signal_id: String::new(),
                            success: false,
                            error: e.message().to_string(),
                        };
                        continue;
                    }
                };

                let test_id = match parse_ulid(&proto_sig.test_id, "test_id") {
                    Ok(id) => id,
                    Err(e) => {
                        yield SignalAck {
                            signal_id: String::new(),
                            success: false,
                            error: e.message().to_string(),
                        };
                        continue;
                    }
                };

                let timestamp = match ms_to_datetime(proto_sig.timestamp, "timestamp") {
                    Ok(ts) => ts,
                    Err(e) => {
                        yield SignalAck {
                            signal_id: String::new(),
                            success: false,
                            error: e.message().to_string(),
                        };
                        continue;
                    }
                };

                // Convert metadata: map<string, string> → HashMap<String, serde_json::Value>
                let metadata: HashMap<String, serde_json::Value> = proto_sig
                    .metadata
                    .into_iter()
                    .map(|(k, v)| (k, serde_json::Value::String(v)))
                    .collect();

                let signal = SignalEntity {
                    id: signal_id,
                    run_id,
                    test_id,
                    signal_type: map_signal_type(&proto_sig.signal_type),
                    timestamp,
                    latency_ms: proto_sig.latency_ms,
                    payload_ref: None,
                    metadata,
                    created_at: BiTemporalTime::now(),
                };

                match db.put_signal(&signal) {
                    Ok(_) => yield SignalAck {
                        signal_id: signal_id.to_string(),
                        success: true,
                        error: String::new(),
                    },
                    Err(e) => yield SignalAck {
                        signal_id: signal_id.to_string(),
                        success: false,
                        error: format!("Failed to store signal: {}", e),
                    },
                }
            }
        };

        Ok(Response::new(Box::pin(output) as Self::StreamSignalsStream))
    }
}
