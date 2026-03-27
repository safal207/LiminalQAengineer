use crate::{
    entities::Signal,
    types::{SignalType, TestStatus},
};

pub struct FlakeDetector {
    window_size: usize,
    threshold: f64,
}

impl Default for FlakeDetector {
    fn default() -> Self {
        Self {
            window_size: 10,
            threshold: 0.3,
        }
    }
}

impl FlakeDetector {
    pub fn new(window_size: usize, threshold: f64) -> Self {
        Self {
            window_size,
            threshold,
        }
    }

    pub fn calculate_score(&self, history: &[TestStatus]) -> f64 {
        if history.len() < 2 {
            return 0.0;
        }

        let relevant_history: Vec<bool> = history
            .iter()
            .filter_map(|s| match s {
                TestStatus::Pass => Some(true),
                TestStatus::Fail | TestStatus::Timeout => Some(false),
                _ => None,
            })
            .collect();

        if relevant_history.len() < 2 {
            return 0.0;
        }

        let mut switches = 0;

        // We only consider the last `window_size` entries if history is longer
        let window = if relevant_history.len() > self.window_size {
            &relevant_history[relevant_history.len() - self.window_size..]
        } else {
            &relevant_history[..]
        };

        // Re-calculate prev for the window start
        let mut prev = window[0];

        for &status in window.iter().skip(1) {
            if status != prev {
                switches += 1;
            }
            prev = status;
        }

        switches as f64 / self.window_size as f64
    }

    pub fn is_flaky(&self, history: &[TestStatus]) -> bool {
        self.calculate_score(history) > self.threshold
    }
}

/// Pass rate over a history slice: `passes / total` (0.0–1.0).
/// Returns 1.0 for empty or all-skip histories.
pub fn stability_score(history: &[TestStatus]) -> f64 {
    let relevant: Vec<_> = history
        .iter()
        .filter(|s| !matches!(s, TestStatus::Skip | TestStatus::XFail))
        .collect();
    if relevant.is_empty() {
        return 1.0;
    }
    let passes = relevant
        .iter()
        .filter(|s| matches!(s, TestStatus::Pass))
        .count();
    passes as f64 / relevant.len() as f64
}

// ---------------------------------------------------------------------------
// Signal importance scoring
// ---------------------------------------------------------------------------

/// Weights and scoring for observed signals.
///
/// `importance = type_weight × latency_factor`
///
/// - `type_weight`   — how critical this signal class is (0.5–1.0)
/// - `latency_factor` — 1.0 (no latency) … 2.0 (≥ 5 000 ms)
///
/// Range: 0.5 (System, 0 ms) to 2.0 (API, 5 s+).
pub struct SignalImportance;

impl SignalImportance {
    /// Base importance weight for a signal type.
    pub fn type_weight(signal_type: SignalType) -> f64 {
        match signal_type {
            SignalType::API => 1.00,
            SignalType::Database => 0.95,
            SignalType::UI => 0.90,
            SignalType::GRPC => 0.85,
            SignalType::WebSocket => 0.75,
            SignalType::Network => 0.60,
            SignalType::System => 0.50,
        }
    }

    /// Compute the importance score for a signal (higher = more noteworthy).
    pub fn compute(signal: &Signal) -> f64 {
        let tw = Self::type_weight(signal.signal_type);
        let latency_ms = signal.latency_ms.unwrap_or(0) as f64;
        // Latency factor: 1.0 at 0 ms, 2.0 at ≥ 5 000 ms
        let latency_factor = 1.0 + (latency_ms.min(5_000.0) / 5_000.0);
        tw * latency_factor
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_flaky_detection() {
        let detector = FlakeDetector::new(10, 0.3);

        let stable_pass = vec![TestStatus::Pass; 10];
        assert_eq!(detector.calculate_score(&stable_pass), 0.0);
        assert!(!detector.is_flaky(&stable_pass));

        let stable_fail = vec![TestStatus::Fail; 10];
        assert_eq!(detector.calculate_score(&stable_fail), 0.0);
        assert!(!detector.is_flaky(&stable_fail));

        // P F P F P F... (switches every time)
        // 10 items. P, F, P, F, P, F, P, F, P, F
        // Switches: 9. Score: 0.9.
        let mut oscillating = vec![];
        for i in 0..10 {
            oscillating.push(if i % 2 == 0 {
                TestStatus::Pass
            } else {
                TestStatus::Fail
            });
        }
        assert_eq!(detector.calculate_score(&oscillating), 0.9);
        assert!(detector.is_flaky(&oscillating));

        // P P P F F F P P P (2 switches: P->F, F->P)
        // Score: 2 / 10 = 0.2 < 0.3
        let few_switches = vec![
            TestStatus::Pass,
            TestStatus::Pass,
            TestStatus::Pass,
            TestStatus::Fail,
            TestStatus::Fail,
            TestStatus::Fail,
            TestStatus::Pass,
            TestStatus::Pass,
            TestStatus::Pass,
            TestStatus::Pass,
        ];
        assert_eq!(detector.calculate_score(&few_switches), 0.2);
        assert!(!detector.is_flaky(&few_switches));
    }
}
