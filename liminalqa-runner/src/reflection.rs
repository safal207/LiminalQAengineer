//! Reflection — Causality-based test reporting

use crate::council::ReconciliationResult;
use liminalqa_core::{entities::Test, types::TestStatus};
use serde::{Deserialize, Serialize};

/// Reflection is the story of what happened during test execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Reflection {
    pub test_id: ulid::Ulid,
    pub test_name: String,
    pub guidance: String,
    pub outcome: Outcome,
    pub causality_trail: Vec<CausalityNode>,
    pub reconciliation: Option<ReconciliationResult>,
    pub insights: Vec<String>,
}

impl Reflection {
    pub fn from_test(test: &Test) -> Self {
        Self {
            test_id: test.id,
            test_name: test.name.clone(),
            guidance: test.guidance.clone(),
            outcome: Outcome::from_status(test.status),
            causality_trail: vec![],
            reconciliation: None,
            insights: vec![],
        }
    }

    pub fn with_reconciliation(mut self, reconciliation: ReconciliationResult) -> Self {
        // Generate insights from reconciliation
        if !reconciliation.inconsistencies.is_empty() {
            self.insights.push(format!(
                "Found {} signal inconsistencies",
                reconciliation.inconsistencies.len()
            ));
        }

        if !reconciliation.patterns.is_empty() {
            self.insights.push(format!(
                "Detected {} behavioral patterns",
                reconciliation.patterns.len()
            ));
        }

        self.reconciliation = Some(reconciliation);
        self
    }

    pub fn add_causality_node(mut self, node: CausalityNode) -> Self {
        self.causality_trail.push(node);
        self
    }

    pub fn add_insight(mut self, insight: impl Into<String>) -> Self {
        self.insights.push(insight.into());
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Outcome {
    Success { duration_ms: u64 },
    Failure { reason: String, duration_ms: u64 },
    Flake { reason: String, attempts: u32 },
    Timeout { after_ms: u64 },
}

impl Outcome {
    fn from_status(status: TestStatus) -> Self {
        match status {
            TestStatus::Pass => Self::Success { duration_ms: 0 },
            TestStatus::Fail => Self::Failure {
                reason: "Unknown".to_string(),
                duration_ms: 0,
            },
            TestStatus::Flake => Self::Flake {
                reason: "Inconsistent behavior".to_string(),
                attempts: 1,
            },
            TestStatus::Timeout => Self::Timeout { after_ms: 0 },
            TestStatus::XFail => Self::Failure {
                reason: "Expected failure".to_string(),
                duration_ms: 0,
            },
            TestStatus::Skip => Self::Success { duration_ms: 0 },
        }
    }
}

/// A node in the causality trail
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CausalityNode {
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub event: String,
    pub source: CausalitySource,
    pub impact: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum CausalitySource {
    UI,
    API,
    WebSocket,
    GRPC,
    Database,
    Network,
    System,
}

impl CausalityNode {
    pub fn new(event: impl Into<String>, source: CausalitySource) -> Self {
        Self {
            timestamp: chrono::Utc::now(),
            event: event.into(),
            source,
            impact: None,
        }
    }

    pub fn with_impact(mut self, impact: impl Into<String>) -> Self {
        self.impact = Some(impact.into());
        self
    }
}
