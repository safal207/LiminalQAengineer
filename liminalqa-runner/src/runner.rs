//! Test runner orchestration

use crate::{
    conavigation::CoNavigator, council::InnerCouncil, guidance::Guidance, reflection::Reflection,
};
use anyhow::Result;
use async_trait::async_trait;
use liminalqa_core::{
    entities::Test, resonance::stability_score, retry::RetryPolicy, temporal::BiTemporalTime,
    triage::TriageEngine, types::*,
};
use serde::{Deserialize, Serialize};
use tracing::info;

/// Test runner that orchestrates the testing philosophy.
///
/// When constructed with [`TestRunner::with_history`] the runner automatically
/// derives a [`RetryPolicy`] from the test's triage verdict before execution,
/// so flaky tests get more attempts and confirmed regressions get zero retries.
pub struct TestRunner {
    run_id: EntityId,
    navigator: CoNavigator,
    triage_engine: TriageEngine,
}

impl TestRunner {
    pub fn new(run_id: EntityId) -> Self {
        Self {
            run_id,
            navigator: CoNavigator::default(),
            triage_engine: TriageEngine::default(),
        }
    }

    pub fn with_navigator(mut self, navigator: CoNavigator) -> Self {
        self.navigator = navigator;
        self
    }

    /// Supply recent test history so the runner can derive an adaptive retry
    /// policy before execution.
    ///
    /// `history` — slice of recent [`TestStatus`] values for this test,
    ///              **oldest first, newest last**.
    pub fn with_history(mut self, history: &[TestStatus]) -> Self {
        let verdict = self.triage_engine.classify(history);
        let stab = stability_score(history);
        let policy = RetryPolicy::from_triage(&verdict, stab);
        info!(
            "Adaptive retry: verdict={:?}  stability={:.0}%  → {}",
            verdict,
            stab * 100.0,
            policy.describe()
        );
        self.navigator = self.navigator.with_policy(policy);
        self
    }

    /// Execute a test following the LIMINAL philosophy.
    pub async fn execute<T: TestCase>(&self, test_case: &T) -> Result<ExecutionResult> {
        let guidance = test_case.guidance();
        let test_id = new_entity_id();

        info!(
            "Executing test: {} ({}) — policy: {}",
            test_case.name(),
            guidance.intent,
            self.navigator.policy.describe(),
        );

        let start = chrono::Utc::now();

        // Run with adaptive retry
        let (outcome, attempts) = self
            .navigator
            .execute_with_retry(test_case.name(), |_attempt| {
                let navigator = &self.navigator;
                async move {
                    let mut council = InnerCouncil::new();
                    test_case
                        .execute(navigator, &mut council)
                        .await
                        .map(|_| council)
                        .map_err(|e| e.to_string())
                }
            })
            .await;

        let end = chrono::Utc::now();
        let duration_ms = (end - start).num_milliseconds() as u64;

        let (status, council) = match outcome {
            Ok(c) => (TestStatus::Pass, c),
            Err(_) => (TestStatus::Fail, InnerCouncil::new()),
        };

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

        let reconciliation = council.reconcile();
        let reflection = Reflection::from_test(&test).with_reconciliation(reconciliation);

        Ok(ExecutionResult {
            test,
            reflection,
            signals: council.signals().to_vec(),
            attempts,
            policy: self.navigator.policy.clone(),
        })
    }
}

/// Trait for test cases
#[async_trait]
pub trait TestCase: Send + Sync {
    fn name(&self) -> &str;
    fn suite(&self) -> &str;
    fn guidance(&self) -> Guidance;
    async fn execute(&self, navigator: &CoNavigator, council: &mut InnerCouncil) -> Result<()>;
}

/// Result of test execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionResult {
    pub test: Test,
    pub reflection: Reflection,
    pub signals: Vec<liminalqa_core::entities::Signal>,
    /// How many attempts were made (1 = passed first try, no retries needed).
    pub attempts: u32,
    /// The retry policy that was applied.
    pub policy: RetryPolicy,
}
