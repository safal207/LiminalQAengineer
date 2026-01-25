pub struct DriftDetector {
    sigma_threshold: f64,
}

impl Default for DriftDetector {
    fn default() -> Self {
        Self {
            sigma_threshold: 2.0,
        }
    }
}

impl DriftDetector {
    pub fn new(sigma_threshold: f64) -> Self {
        Self { sigma_threshold }
    }

    pub fn calculate_z_score(&self, current: f64, mean: f64, stddev: f64) -> f64 {
        if stddev == 0.0 {
            return 0.0;
        }
        (current - mean) / stddev
    }

    pub fn is_drift(&self, current: f64, mean: f64, stddev: f64) -> bool {
        self.calculate_z_score(current, mean, stddev).abs() > self.sigma_threshold
    }

    pub fn calculate_stats(&self, history: &[f64]) -> (f64, f64) {
        if history.is_empty() {
            return (0.0, 0.0);
        }
        let count = history.len() as f64;
        let mean = history.iter().sum::<f64>() / count;

        if count < 2.0 {
            return (mean, 0.0);
        }

        let variance = history
            .iter()
            .map(|v| {
                let diff = mean - v;
                diff * diff
            })
            .sum::<f64>()
            / (count - 1.0); // Sample stddev? Or population? Usually sample (N-1) for estimation.

        (mean, variance.sqrt())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stats() {
        let detector = DriftDetector::default();
        let data = vec![10.0, 12.0, 11.0, 13.0, 9.0]; // Mean 11, small stddev
        let (mean, stddev) = detector.calculate_stats(&data);
        assert_eq!(mean, 11.0);
        assert!(stddev > 0.0);
    }

    #[test]
    fn test_drift() {
        let detector = DriftDetector::new(2.0);
        let mean = 100.0;
        let stddev = 10.0;

        // 110 is 1 sigma -> No drift
        assert!(!detector.is_drift(110.0, mean, stddev));

        // 125 is 2.5 sigma -> Drift
        assert!(detector.is_drift(125.0, mean, stddev));

        // 75 is -2.5 sigma -> Drift (abs)
        assert!(detector.is_drift(75.0, mean, stddev));
    }
}
