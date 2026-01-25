//! LiminalQA Runner — Test execution engine
//!
//! Philosophy: Guidance → Co-Navigation → Council → Reflection
//!
//! - Guidance: Test intention (what we want to observe)
//! - Co-Navigation: Adaptive execution (retries, timeouts, flexible waits)
//! - Inner Council: Signal reconciliation (UI/API/WS/gRPC unified view)
//! - Reflection: Causality-based reporting

pub mod conavigation;
pub mod council;
pub mod guidance;
pub mod ingest;
pub mod metrics;
pub mod reflection;
pub mod runner;

pub use conavigation::CoNavigator;
pub use council::InnerCouncil;
pub use guidance::Guidance;
pub use ingest::{create_ingest, Ingest, IngestConfig};
pub use metrics::TestMetrics;
pub use reflection::Reflection;
pub use runner::TestRunner;
