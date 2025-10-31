//! Co-Navigation — Adaptive test execution with retries and flexible waits

use anyhow::Result;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tracing::{debug, warn};

/// Co-Navigator handles adaptive execution strategies
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoNavigator {
    pub max_retries: u32,
    pub retry_delay_ms: u64,
    pub flexible_wait_ms: u64,
}

impl Default for CoNavigator {
    fn default() -> Self {
        Self {
            max_retries: 3,
            retry_delay_ms: 1000,
            flexible_wait_ms: 5000,
        }
    }
}

impl CoNavigator {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_retries(mut self, max_retries: u32) -> Self {
        self.max_retries = max_retries;
        self
    }

    pub fn with_retry_delay(mut self, delay_ms: u64) -> Self {
        self.retry_delay_ms = delay_ms;
        self
    }

    /// Execute with automatic retries on failure
    pub async fn execute_with_retry<F, Fut, T, E>(
        &self,
        operation: F,
    ) -> Result<T, E>
    where
        F: Fn() -> Fut,
        Fut: std::future::Future<Output = Result<T, E>>,
        E: std::fmt::Display,
    {
        let mut attempts = 0;

        loop {
            attempts += 1;

            match operation().await {
                Ok(result) => {
                    if attempts > 1 {
                        debug!("Operation succeeded after {} attempts", attempts);
                    }
                    return Ok(result);
                }
                Err(e) => {
                    if attempts >= self.max_retries {
                        warn!("Operation failed after {} attempts: {}", attempts, e);
                        return Err(e);
                    }

                    warn!("Attempt {} failed: {}. Retrying...", attempts, e);
                    tokio::time::sleep(Duration::from_millis(self.retry_delay_ms)).await;
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
