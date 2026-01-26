use crate::liminalqa::v1::{
    ingest_service_server::IngestService, IngestRunRequest, IngestRunResponse, IngestTestsRequest,
    IngestTestsResponse, Signal, SignalAck,
};
use chrono::{TimeZone, Utc};
use liminalqa_core::types::EntityId;
use liminalqa_db::{models::TestRun, PostgresStorage};
use std::pin::Pin;
use tokio_stream::Stream;
use tokio_stream::StreamExt;
use tonic::{Request, Response, Status};

pub struct MyIngestService {
    db: PostgresStorage,
}

impl MyIngestService {
    pub fn new(db: PostgresStorage) -> Self {
        Self { db }
    }
}

#[tonic::async_trait]
impl IngestService for MyIngestService {
    async fn ingest_run(
        &self,
        request: Request<IngestRunRequest>,
    ) -> Result<Response<IngestRunResponse>, Status> {
        let req = request.into_inner();

        let run_id = liminalqa_core::types::new_entity_id();

        let _build_id = EntityId::from_string(&req.build_id)
            .map_err(|e| Status::invalid_argument(format!("Invalid build_id: {}", e)))?;

        let env: std::collections::HashMap<String, String> = serde_json::from_str(&req.env)
            .map_err(|e| Status::invalid_argument(format!("Invalid env JSON: {}", e)))?;
        let env_json = serde_json::to_value(env).map_err(|e| Status::internal(e.to_string()))?;

        let started_at = chrono::Utc
            .timestamp_millis_opt(req.started_at)
            .single()
            .ok_or_else(|| Status::invalid_argument("Invalid started_at timestamp"))?;

        let run = TestRun {
            id: run_id.to_string(),
            build_id: Some(req.build_id),
            plan_name: req.plan_name,
            status: "running".to_string(),
            started_at,
            completed_at: None,
            duration_ms: None,
            environment: Some(env_json),
            metadata: None,
            created_at: Utc::now(),
            protocol_version: None,
            self_resonance_score: None,
            world_resonance_score: None,
            overall_alignment_score: None,
        };

        self.db
            .insert_run(&run)
            .await
            .map_err(|e| Status::internal(format!("Failed to store run: {}", e)))?;

        Ok(Response::new(IngestRunResponse {
            run_id: run_id.to_string(),
        }))
    }

    async fn ingest_tests(
        &self,
        request: Request<IngestTestsRequest>,
    ) -> Result<Response<IngestTestsResponse>, Status> {
        let req = request.into_inner();

        let _run_id = EntityId::from_string(&req.run_id)
            .map_err(|e| Status::invalid_argument(format!("Invalid run_id: {}", e)))?;

        // TODO: Implement test ingestion mapping from proto Test to entity Test
        // For Phase 4 MVP this is stubbed as per original file

        Ok(Response::new(IngestTestsResponse {
            processed_count: req.tests.len() as i32,
            failed_count: 0,
            failed_ids: vec![],
        }))
    }

    type StreamSignalsStream = Pin<Box<dyn Stream<Item = Result<SignalAck, Status>> + Send>>;

    async fn stream_signals(
        &self,
        request: Request<tonic::Streaming<Signal>>,
    ) -> Result<Response<Self::StreamSignalsStream>, Status> {
        let mut stream = request.into_inner();
        let _db = self.db.clone();

        let output = async_stream::try_stream! {
            while let Some(signal) = stream.next().await {
                let _sig = signal?;
                // TODO: Save signal to DB using `db`
                // Parsing signal fields and calling db.put_signal

                yield SignalAck {
                    signal_id: ulid::Ulid::new().to_string(),
                    success: true,
                    error: "".to_string(),
                };
            }
        };

        Ok(Response::new(Box::pin(output) as Self::StreamSignalsStream))
    }
}
