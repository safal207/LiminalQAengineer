pub mod liminalqa {
    // tonic generates client methods returning tonic::Status; keep this
    // dependency-owned API out of workspace-wide `-D warnings` enforcement.
    #[allow(clippy::result_large_err)]
    pub mod v1 {
        tonic::include_proto!("liminalqa.v1");
    }
}

pub mod server;

pub use liminalqa::v1::ingest_service_server::{IngestService, IngestServiceServer};
pub use liminalqa::v1::{
    IngestRunRequest, IngestRunResponse, IngestTestsRequest, IngestTestsResponse, Signal, SignalAck,
};
pub use server::MyIngestService;
