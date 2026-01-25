use crate::types::TestStatus;

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
