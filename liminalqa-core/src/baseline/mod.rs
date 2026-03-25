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

// ---------------------------------------------------------------------------
// Noise filtering
// ---------------------------------------------------------------------------

/// Remove statistical outliers from a latency/metric slice so that load-induced
/// spikes don't pollute flakiness or drift calculations.
///
/// Two strategies are available:
///  * Z-score — removes values whose |z| exceeds `threshold` (default 3.0).
///  * IQR     — removes values outside `[Q1 − k·IQR, Q3 + k·IQR]` (default k=1.5).
///
/// Both return a *new* `Vec<f64>` with outliers omitted.
pub struct NoiseFilter;

impl NoiseFilter {
    /// Remove values with |z-score| > `threshold`.
    /// Returns `values` unchanged if there are fewer than 2 data points.
    pub fn filter_zscore(values: &[f64], threshold: f64) -> Vec<f64> {
        if values.len() < 2 {
            return values.to_vec();
        }
        let n = values.len() as f64;
        let mean = values.iter().sum::<f64>() / n;
        let variance = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1.0);
        let stddev = variance.sqrt();
        if stddev == 0.0 {
            return values.to_vec();
        }
        values
            .iter()
            .copied()
            .filter(|&v| ((v - mean) / stddev).abs() <= threshold)
            .collect()
    }

    /// Remove values outside the fences `[Q1 − k·IQR, Q3 + k·IQR]`.
    /// Returns `values` unchanged if there are fewer than 4 data points.
    pub fn filter_iqr(values: &[f64], k: f64) -> Vec<f64> {
        if values.len() < 4 {
            return values.to_vec();
        }
        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let q1 = Self::percentile(&sorted, 25.0);
        let q3 = Self::percentile(&sorted, 75.0);
        let iqr = q3 - q1;
        let lo = q1 - k * iqr;
        let hi = q3 + k * iqr;
        values
            .iter()
            .copied()
            .filter(|&v| v >= lo && v <= hi)
            .collect()
    }

    /// Linear-interpolation percentile on a *sorted* slice (0–100).
    fn percentile(sorted: &[f64], p: f64) -> f64 {
        let n = sorted.len();
        if n == 0 {
            return 0.0;
        }
        let index = p / 100.0 * (n - 1) as f64;
        let lo = index.floor() as usize;
        let hi = index.ceil() as usize;
        if lo == hi {
            sorted[lo]
        } else {
            let frac = index - lo as f64;
            sorted[lo] * (1.0 - frac) + sorted[hi] * frac
        }
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

    #[test]
    fn test_zscore_filter_removes_spike() {
        // 99 normal values around 100, one extreme spike at 9_000
        let mut data: Vec<f64> = (0..99).map(|i| 95.0 + (i % 10) as f64).collect();
        data.push(9_000.0);
        let filtered = NoiseFilter::filter_zscore(&data, 3.0);
        assert!(filtered.len() < data.len(), "spike should be removed");
        assert!(!filtered.contains(&9_000.0));
    }

    #[test]
    fn test_zscore_filter_uniform() {
        // All identical — stddev = 0, nothing removed
        let data = vec![50.0; 10];
        let filtered = NoiseFilter::filter_zscore(&data, 3.0);
        assert_eq!(filtered.len(), 10);
    }

    #[test]
    fn test_iqr_filter_removes_outliers() {
        // Values tightly clustered around 100, two extreme outliers
        let mut data: Vec<f64> = (0..20).map(|_| 100.0).collect();
        data.push(1_000.0);
        data.push(-500.0);
        let filtered = NoiseFilter::filter_iqr(&data, 1.5);
        assert!(!filtered.contains(&1_000.0));
        assert!(!filtered.contains(&-500.0));
        assert_eq!(filtered.len(), 20);
    }

    #[test]
    fn test_iqr_too_small_returns_unchanged() {
        let data = vec![1.0, 2.0, 3.0];
        let filtered = NoiseFilter::filter_iqr(&data, 1.5);
        assert_eq!(filtered, data);
    }
}
