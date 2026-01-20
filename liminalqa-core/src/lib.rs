//! LiminalQA Core — fundamental types and data model
//!
//! This module defines the bi-temporal entity model:
//! - Entities: System, Build, Run, Test, Artifact, Signal, Resonance
//! - Temporal axes: valid_time (truth of the world) & tx_time (when we learned)
//! - Facts: attributes attached to entities across time

pub mod entities;
pub mod facts;
pub mod report;
pub mod temporal;
pub mod types;

pub use entities::*;
pub use facts::*;
pub use report::*;
pub use temporal::*;
pub use types::*;
