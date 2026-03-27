//! Co-Navigation — Adaptive test execution with retries and flexible waits

use anyhow::Result;
use async_trait::async_trait;
use liminalqa_core::retry::RetryPolicy;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tracing::{debug, warn};

/// Co-Navigator handles adaptive execution strategies.
///
/// The `policy` field drives how many retries are attempted and with what
/// delay. Use [`CoNavigator::with_policy`] to supply a triage-derived
/// [`RetryPolicy`]; the navigator falls back to `RetryPolicy::default()`
/// (one retry, 1 s delay) when history is unavailable.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoNavigator {
    /// Adaptive retry policy — derived from triage verdict at runtime.
    pub policy: RetryPolicy,
    pub flexible_wait_ms: u64,
}

impl Default for CoNavigator {
    fn default() -> Self {
        Self {
            policy: RetryPolicy::default(),
            flexible_wait_ms: 5000,
        }
    }
}

impl CoNavigator {
    pub fn new() -> Self {
        Self::default()
    }

    /// Override the retry policy (e.g. from a triage verdict).
    pub fn with_policy(mut self, policy: RetryPolicy) -> Self {
        self.policy = policy;
        self
    }

    /// Convenience: set a fixed number of retries with a flat delay.
    pub fn with_retries(mut self, max_retries: u32) -> Self {
        self.policy = RetryPolicy::Backoff {
            max_retries,
            base_delay_ms: 1_000,
            max_delay_ms: 8_000,
        };
        self
    }

    /// Execute with retries according to the current [`RetryPolicy`].
    ///
    /// Returns `(result, attempts)` — `attempts` is the total number of
    /// times the operation was called (1 = passed on first try).
    pub async fn execute_with_retry<F, Fut, T, E>(
        &self,
        test_name: &str,
        operation: F,
    ) -> (Result<T, E>, u32)
    where
        F: Fn(u32) -> Fut,
        Fut: std::future::Future<Output = Result<T, E>>,
        E: std::fmt::Display,
    {
        let max_retries = self.policy.max_retries();
        let mut attempt = 0u32;
        debug!(
            "execute_with_retry: {} — {}",
            test_name,
            self.policy.describe()
        );
        loop {
            let result = operation(attempt).await;
            match result {
                Ok(v) => {
                    if attempt > 0 {
                        debug!("{}: passed on attempt {}", test_name, attempt + 1);
                    }
                    return (Ok(v), attempt + 1);
                }
                Err(e) => {
                    if attempt >= max_retries {
                        warn!(
                            "{}: failed after {} attempt(s): {}",
                            test_name,
                            attempt + 1,
                            e
                        );
                        return (Err(e), attempt + 1);
                    }
                    let delay = self.policy.delay_for(attempt);
                    warn!(
                        "{}: attempt {} failed, retrying in {:?}: {}",
                        test_name,
                        attempt + 1,
                        delay,
                        e
                    );
                    tokio::time::sleep(delay).await;
                    attempt += 1;
                }
            }
        }
    }

    /// Flexible wait with exponential backoff
    pub async fn flexible_wait(&self, base_ms: u64, max_attempts: u32) {
        for attempt in 0..max_attempts {
            let delay_ms = base_ms * 2_u64.pow(attempt);
            tokio::time::sleep(Duration::from_millis(delay_ms)).await;
        }
    }
}

#[async_trait]
pub trait Navigable {
    async fn navigate(&self, navigator: &CoNavigator) -> Result<NavigationResult>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NavigationResult {
    pub success: bool,
    pub attempts: u32,
    pub duration_ms: u64,
    pub notes: Vec<String>,
}

impl NavigationResult {
    pub fn success(attempts: u32, duration_ms: u64) -> Self {
        Self {
            success: true,
            attempts,
            duration_ms,
            notes: vec![],
        }
    }

    pub fn failure(attempts: u32, duration_ms: u64, error: String) -> Self {
        Self {
            success: false,
            attempts,
            duration_ms,
            notes: vec![error],
        }
    }

    pub fn with_note(mut self, note: String) -> Self {
        self.notes.push(note);
        self
    }
}
