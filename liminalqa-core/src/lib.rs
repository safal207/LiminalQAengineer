//! LiminalQA Core — fundamental types and data model
//!
//! This module defines the bi-temporal entity model:
//! - Entities: System, Build, Run, Test, Artifact, Signal, Resonance
//! - Temporal axes: valid_time (truth of the world) & tx_time (when we learned)
//! - Facts: attributes attached to entities across time

pub mod baseline;
pub mod causality;
pub mod cgqa_interop;
pub mod community;
pub mod context;
pub mod dashboard;
pub mod decision;
pub mod entities;
pub mod export;
pub mod facts;
pub mod metrics;
pub mod report;
pub mod resonance;
pub mod retry;
pub mod rootcause;
pub mod suite_policy;
pub mod temporal;
pub mod triage;
pub mod types;

pub use entities::*;
pub use facts::*;
pub use metrics::*;
pub use report::*;
pub use suite_policy::evaluate_suite_strict;
pub use temporal::*;
pub use types::*;
