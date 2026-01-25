use crate::liminalqa::v1::{
    ingest_service_server::IngestService, IngestRunRequest, IngestRunResponse, IngestTestsRequest,
    IngestTestsResponse, Signal, SignalAck,
};
use liminalqa_db::LiminalDB;
use std::sync::Arc;
use tonic::{Request, Response, Status};
use tokio_stream::StreamExt;
use std::pin::Pin;
use tokio_stream::Stream;
use liminalqa_core::types::EntityId;
use chrono::TimeZone;

pub struct MyIngestService {
    db: Arc<LiminalDB>,
}

impl MyIngestService {
    pub fn new(db: Arc<LiminalDB>) -> Self {
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

        let build_id = EntityId::from_string(&req.build_id)
            .map_err(|e| Status::invalid_argument(format!("Invalid build_id: {}", e)))?;

        let env: std::collections::HashMap<String, String> = serde_json::from_str(&req.env)
             .map_err(|e| Status::invalid_argument(format!("Invalid env JSON: {}", e)))?;

        let started_at = chrono::Utc.timestamp_millis_opt(req.started_at).single()
            .ok_or_else(|| Status::invalid_argument("Invalid started_at timestamp"))?;

        let ended_at = if let Some(ts) = req.ended_at {
             Some(chrono::Utc.timestamp_millis_opt(ts).single()
                 .ok_or_else(|| Status::invalid_argument("Invalid ended_at timestamp"))?)
        } else {
             None
        };

        let run = liminalqa_core::entities::Run {
            id: run_id,
            build_id,
            plan_name: req.plan_name,
            env,
            started_at,
            ended_at,
            runner_version: req.runner_version,
            liminal_os_version: req.liminal_os_version,
            created_at: liminalqa_core::temporal::BiTemporalTime::now(),
        };

        self.db.put_run(&run)
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
