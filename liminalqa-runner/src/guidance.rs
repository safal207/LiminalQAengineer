//! Guidance — Test intention and observable goals

use serde::{Deserialize, Serialize};

/// Guidance defines what we want to observe in the system
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Guidance {
    /// Human-readable description of test intent
    pub intent: String,

    /// Observable conditions that should be met
    pub observables: Vec<Observable>,

    /// Timeout for overall guidance (ms)
    pub timeout_ms: u64,

    /// Whether this is a happy path or edge case
    pub category: GuidanceCategory,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Observable {
    /// UI element should be visible
    UiVisible { selector: String },

    /// UI element should contain text
    UiContainsText { selector: String, text: String },

    /// API should return specific status
    ApiStatus { endpoint: String, status: u16 },

    /// WebSocket should receive message
    WsMessage { pattern: String },

    /// gRPC call should succeed
    GrpcSuccess { method: String },

    /// Custom condition
    Custom { description: String },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum GuidanceCategory {
    HappyPath,
    EdgeCase,
    ErrorHandling,
    Performance,
    Security,
}

impl Guidance {
    pub fn new(intent: impl Into<String>) -> Self {
        Self {
            intent: intent.into(),
            observables: vec![],
            timeout_ms: 30_000, // 30s default
            category: GuidanceCategory::HappyPath,
        }
    }

    pub fn with_observable(mut self, observable: Observable) -> Self {
        self.observables.push(observable);
        self
    }

    pub fn with_timeout(mut self, timeout_ms: u64) -> Self {
        self.timeout_ms = timeout_ms;
        self
    }

    pub fn with_category(mut self, category: GuidanceCategory) -> Self {
        self.category = category;
        self
    }
}
