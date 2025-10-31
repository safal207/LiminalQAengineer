//! Test runner orchestration

use crate::{
    conavigation::CoNavigator, council::InnerCouncil, guidance::Guidance, reflection::Reflection,
};
use anyhow::Result;
use async_trait::async_trait;
use liminalqa_core::{entities::Test, temporal::BiTemporalTime, types::*};
use serde::{Deserialize, Serialize};
use tracing::info;

/// Test runner that orchestrates the testing philosophy
pub struct TestRunner {
    run_id: EntityId,
    navigator: CoNavigator,
}

impl TestRunner {
    pub fn new(run_id: EntityId) -> Self {
        Self {
            run_id,
            navigator: CoNavigator::default(),
        }
    }

    pub fn with_navigator(mut self, navigator: CoNavigator) -> Self {
        self.navigator = navigator;
        self
    }

    /// Execute a test following the LIMINAL philosophy
    pub async fn execute<T: TestCase>(&self, test_case: &T) -> Result<ExecutionResult> {
        let guidance = test_case.guidance();
        let test_id = new_entity_id();

        info!(
            "Executing test: {} ({})",
            test_case.name(),
            guidance.intent
        );

        let start = chrono::Utc::now();
        let mut council = InnerCouncil::new();

        // Execute test with co-navigation
        let status = match test_case.execute(&self.navigator, &mut council).await {
            Ok(_) => TestStatus::Pass,
            Err(e) => {
                tracing::error!("Test failed: {}", e);
                TestStatus::Fail
            }
        };

        let end = chrono::Utc::now();
        let duration_ms = (end - start).num_milliseconds() as u64;

        // Create test entity
        let test = Test {
            id: test_id,
            run_id: self.run_id,
            name: test_case.name().to_string(),
            suite: test_case.suite().to_string(),
            guidance: guidance.intent.clone(),
            status,
            duration_ms,
            error: None,
            started_at: start,
            completed_at: end,
            created_at: BiTemporalTime::now(),
        };

        // Generate reflection
        let reconciliation = council.reconcile();
        let reflection = Reflection::from_test(&test).with_reconciliation(reconciliation);

        Ok(ExecutionResult {
            test,
            reflection,
            signals: council.signals().to_vec(),
        })
    }
}

/// Trait for test cases
#[async_trait]
pub trait TestCase: Send + Sync {
    fn name(&self) -> &str;
    fn suite(&self) -> &str;
    fn guidance(&self) -> Guidance;
    async fn execute(
        &self,
        navigator: &CoNavigator,
        council: &mut InnerCouncil,
    ) -> Result<()>;
}

/// Result of test execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionResult {
    pub test: Test,
    pub reflection: Reflection,
    pub signals: Vec<liminalqa_core::entities::Signal>,
}
