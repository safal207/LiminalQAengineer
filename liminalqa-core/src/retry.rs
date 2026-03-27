//! Adaptive retry policy derived from triage verdicts.
//!
//! Instead of a fixed `max_retries = 3` for every test, `RetryPolicy`
//! adjusts the number of attempts and backoff strategy based on what the
//! triage engine knows about a test's history:
//!
//! | Verdict       | Policy                            | Reasoning |
//! |---------------|-----------------------------------|-----------|
//! | `NewBug`      | None (0 retries)                  | Real regression — retrying wastes time and hides signal |
//! | `Stable`      | Once (1 retry, short delay)       | Should pass; one extra chance for transient infra noise |
//! | `KnownIssue`  | Once (1 retry, medium delay)      | Already tracked; confirm it's still failing |
//! | `Flake`       | Backoff (3–5 retries)             | Known flaky — keep trying, exponential backoff |
//!
//! The stability score further adjusts flake retries:
//! stability < 50% → 5 retries, otherwise 3.

use crate::triage::TriageVerdict;
use serde::{Deserialize, Serialize};
use std::time::Duration;

// ---------------------------------------------------------------------------
// RetryPolicy
// ---------------------------------------------------------------------------

/// How many times and how long to retry a failed test execution.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum RetryPolicy {
    /// Never retry. The test outcome is taken as-is.
    None,
    /// Retry exactly once after `delay_ms` milliseconds.
    Once { delay_ms: u64 },
    /// Exponential backoff: up to `max_retries` additional attempts.
    /// Delay = `base_delay_ms × 2^attempt`, capped at `max_delay_ms`.
    Backoff {
        max_retries: u32,
        base_delay_ms: u64,
        max_delay_ms: u64,
    },
}

impl Default for RetryPolicy {
    /// Sensible default when history is unknown: one retry, 1 s delay.
    fn default() -> Self {
        RetryPolicy::Once { delay_ms: 1_000 }
    }
}

impl RetryPolicy {
    /// Derive the retry policy from a triage verdict and stability score.
    ///
    /// `stability` is in 0.0–1.0 (1.0 = always passes).
    pub fn from_triage(verdict: &TriageVerdict, stability: f64) -> Self {
        match verdict {
            // Real regression — one attempt, no retries
            TriageVerdict::NewBug => RetryPolicy::None,

            // Stable tests shouldn't need retries; one safety net
            TriageVerdict::Stable => RetryPolicy::Once { delay_ms: 500 },

            // Known issue — confirm it's still failing, don't waste many cycles
            TriageVerdict::KnownIssue => RetryPolicy::Once { delay_ms: 1_000 },

            // Flaky — keep retrying with backoff; more retries for very unstable tests
            TriageVerdict::Flake => {
                let max_retries = if stability < 0.5 { 5 } else { 3 };
                RetryPolicy::Backoff {
                    max_retries,
                    base_delay_ms: 500,
                    max_delay_ms: 8_000,
                }
            }
        }
    }

    /// Maximum number of *additional* attempts (0 = no retry, just the initial run).
    pub fn max_retries(&self) -> u32 {
        match self {
            RetryPolicy::None => 0,
            RetryPolicy::Once { .. } => 1,
            RetryPolicy::Backoff { max_retries, .. } => *max_retries,
        }
    }

    /// Delay before attempt number `attempt` (0-indexed, 0 = first retry).
    pub fn delay_for(&self, attempt: u32) -> Duration {
        match self {
            RetryPolicy::None => Duration::ZERO,
            RetryPolicy::Once { delay_ms } => Duration::from_millis(*delay_ms),
            RetryPolicy::Backoff {
                base_delay_ms,
                max_delay_ms,
                ..
            } => {
                let ms = base_delay_ms
                    .saturating_mul(2u64.saturating_pow(attempt))
                    .min(*max_delay_ms);
                Duration::from_millis(ms)
            }
        }
    }

    /// Human-readable summary for logs.
    pub fn describe(&self) -> String {
        match self {
            RetryPolicy::None => "no retries (new_bug)".to_string(),
            RetryPolicy::Once { delay_ms } => {
                format!("1 retry after {}ms", delay_ms)
            }
            RetryPolicy::Backoff {
                max_retries,
                base_delay_ms,
                max_delay_ms,
            } => format!(
                "{} retries, backoff {}ms–{}ms (flake)",
                max_retries, base_delay_ms, max_delay_ms
            ),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::triage::TriageVerdict;

    #[test]
    fn new_bug_no_retries() {
        let p = RetryPolicy::from_triage(&TriageVerdict::NewBug, 0.9);
        assert_eq!(p.max_retries(), 0);
        assert_eq!(p, RetryPolicy::None);
    }

    #[test]
    fn stable_one_retry() {
        let p = RetryPolicy::from_triage(&TriageVerdict::Stable, 0.99);
        assert_eq!(p.max_retries(), 1);
    }

    #[test]
    fn flake_high_stability_three_retries() {
        let p = RetryPolicy::from_triage(&TriageVerdict::Flake, 0.7);
        assert_eq!(p.max_retries(), 3);
    }

    #[test]
    fn flake_low_stability_five_retries() {
        let p = RetryPolicy::from_triage(&TriageVerdict::Flake, 0.3);
        assert_eq!(p.max_retries(), 5);
    }

    #[test]
    fn backoff_delay_grows_exponentially() {
        let p = RetryPolicy::Backoff {
            max_retries: 4,
            base_delay_ms: 500,
            max_delay_ms: 8_000,
        };
        assert_eq!(p.delay_for(0), Duration::from_millis(500));
        assert_eq!(p.delay_for(1), Duration::from_millis(1_000));
        assert_eq!(p.delay_for(2), Duration::from_millis(2_000));
        assert_eq!(p.delay_for(4), Duration::from_millis(8_000)); // capped
    }
}
