// ---------------------------------------------------------------------------
// Exponential Moving Average baseline
// ---------------------------------------------------------------------------

/// Online EMA tracker for a single test metric (e.g. duration_ms).
///
/// Unlike a simple rolling mean, EMA gives *more weight to recent observations*
/// and adapts naturally to gradual trends without storing full history.
///
/// ## Formula
///
/// ```text
/// α = 2 / (period + 1)
/// ema_new = α × current + (1 − α) × ema_old
/// ```
///
/// ## Confidence
///
/// Confidence grows from 0 → 1 as more samples are seen, reaching ~63% at
/// `period` samples and ~95% at `3 × period` samples.  Use it to suppress
/// drift alerts when the baseline is still warming up.
///
/// ## Usage
///
/// ```ignore
/// let mut ema = ExponentialBaseline::new(20); // 20-sample smoothing window
/// for duration in history {
///     ema.update(duration);
/// }
/// let (mean, stddev, confidence) = ema.stats();
/// ```
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ExponentialBaseline {
    /// Smoothing period N — higher = slower to adapt (default 20).
    period: u32,
    /// Smoothing factor α = 2 / (period + 1).
    alpha: f64,
    /// Current EMA value.
    ema: f64,
    /// EMA of squared values — used to compute variance online.
    ema_sq: f64,
    /// Number of samples seen so far.
    n: u64,
}

impl ExponentialBaseline {
    /// Create a new baseline with a smoothing period of `period` samples.
    ///
    /// Typical choices: 10 (fast adapt), 20 (balanced), 50 (slow/stable).
    pub fn new(period: u32) -> Self {
        let period = period.max(1);
        let alpha = 2.0 / (period as f64 + 1.0);
        Self {
            period,
            alpha,
            ema: 0.0,
            ema_sq: 0.0,
            n: 0,
        }
    }

    /// Feed a new observation into the baseline.
    pub fn update(&mut self, value: f64) {
        if self.n == 0 {
            // Seed with first value
            self.ema = value;
            self.ema_sq = value * value;
        } else {
            self.ema = self.alpha * value + (1.0 - self.alpha) * self.ema;
            self.ema_sq = self.alpha * value * value + (1.0 - self.alpha) * self.ema_sq;
        }
        self.n += 1;
    }

    /// Returns `(ema_mean, ema_stddev, confidence)`.
    ///
    /// - `ema_mean`   — exponentially-weighted mean
    /// - `ema_stddev` — exponentially-weighted standard deviation
    /// - `confidence` — 0.0–1.0, rises as `n` grows (1.0 after ~3×period samples)
    pub fn stats(&self) -> (f64, f64, f64) {
        if self.n == 0 {
            return (0.0, 0.0, 0.0);
        }
        let variance = (self.ema_sq - self.ema * self.ema).max(0.0);
        let stddev = variance.sqrt();
        // Confidence: sigmoid-shaped curve reaching ≈0.95 at 3×period samples
        let confidence = 1.0 - (-(self.n as f64) / self.period as f64).exp();
        (self.ema, stddev, confidence.min(1.0))
    }

    /// Current EMA mean (shorthand for `stats().0`).
    pub fn mean(&self) -> f64 {
        self.ema
    }

    /// Number of samples seen.
    pub fn sample_count(&self) -> u64 {
        self.n
    }

    /// `true` if enough samples have been seen to trust the baseline
    /// (confidence ≥ 0.5, i.e. at least ~`period / 2` samples).
    pub fn is_warmed_up(&self) -> bool {
        self.n >= (self.period / 2) as u64
    }

    /// Detect drift: returns `true` if `current` deviates more than
    /// `sigma_threshold` standard deviations from the EMA.
    pub fn is_drift(&self, current: f64, sigma_threshold: f64) -> bool {
        let (mean, stddev, _confidence) = self.stats();
        if stddev == 0.0 || !self.is_warmed_up() {
            return false;
        }
        ((current - mean) / stddev).abs() > sigma_threshold
    }

    /// Compute an adaptive timeout as `mean + sigma_factor × stddev`.
    ///
    /// Returns `None` when the baseline is not yet warmed up — the caller
    /// should fall back to a static default.
    ///
    /// Typical value: `sigma_factor = 3.0`  (covers 99.7 % of normal runs).
    pub fn suggested_timeout_ms(&self, sigma_factor: f64) -> Option<u64> {
        if !self.is_warmed_up() {
            return None;
        }
        let (mean, stddev, _) = self.stats();
        let raw = mean + sigma_factor * stddev;
        // Floor at 100 ms, ceil at 10 min — sanity guard
        Some(raw.clamp(100.0, 600_000.0) as u64)
    }
}

// ---------------------------------------------------------------------------
// DurationTrend — online linear regression for test duration over time
// ---------------------------------------------------------------------------

/// Online linear regression: tracks whether test duration is trending up
/// (degrading) or down (improving) over successive runs.
///
/// Uses Welford-style running sums so no history is stored:
/// `y = slope × x + intercept` where x is the sample index (0, 1, 2, …).
///
/// Persist with `serde` — same as `ExponentialBaseline`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DurationTrend {
    n: u64,
    sum_x: f64,
    sum_y: f64,
    sum_xx: f64,
    sum_xy: f64,
    sum_yy: f64,
}

impl DurationTrend {
    pub fn new() -> Self {
        Self {
            n: 0,
            sum_x: 0.0,
            sum_y: 0.0,
            sum_xx: 0.0,
            sum_xy: 0.0,
            sum_yy: 0.0,
        }
    }

    /// Feed the next duration observation (ms).
    pub fn update(&mut self, duration_ms: f64) {
        let x = self.n as f64;
        self.sum_x += x;
        self.sum_y += duration_ms;
        self.sum_xx += x * x;
        self.sum_xy += x * duration_ms;
        self.sum_yy += duration_ms * duration_ms;
        self.n += 1;
    }

    /// Returns `TrendStats` with slope, intercept, and R².
    ///
    /// - `slope > 0` → test getting slower (ms per run)
    /// - `slope < 0` → test getting faster
    /// - `r_squared` → linearity of the trend (0.0 = noise, 1.0 = perfect line)
    ///
    /// Returns `None` when fewer than 3 samples have been collected.
    pub fn regression(&self) -> Option<TrendStats> {
        if self.n < 3 {
            return None;
        }
        let n = self.n as f64;
        let denom = n * self.sum_xx - self.sum_x * self.sum_x;
        if denom == 0.0 {
            return None;
        }
        let slope = (n * self.sum_xy - self.sum_x * self.sum_y) / denom;
        let intercept = (self.sum_y - slope * self.sum_x) / n;

        // R² via Pearson r: r = (n·Σxy − Σx·Σy) / sqrt[(n·Σxx − (Σx)²)(n·Σyy − (Σy)²)]
        let ss_xx = n * self.sum_xx - self.sum_x * self.sum_x;
        let ss_yy = n * self.sum_yy - self.sum_y * self.sum_y;
        let r_squared = if ss_xx > 0.0 && ss_yy > 0.0 {
            let r = (n * self.sum_xy - self.sum_x * self.sum_y) / (ss_xx * ss_yy).sqrt();
            (r * r).min(1.0)
        } else {
            0.0
        };

        Some(TrendStats {
            slope_ms_per_run: slope,
            intercept_ms: intercept,
            r_squared,
            sample_count: self.n,
        })
    }

    pub fn sample_count(&self) -> u64 {
        self.n
    }
}

impl Default for DurationTrend {
    fn default() -> Self {
        Self::new()
    }
}

/// Output of `DurationTrend::regression()`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TrendStats {
    /// Milliseconds per run.  Positive = degrading, negative = improving.
    pub slope_ms_per_run: f64,
    /// Estimated duration at run 0.
    pub intercept_ms: f64,
    /// Coefficient of determination (0.0–1.0).
    pub r_squared: f64,
    /// Number of samples used.
    pub sample_count: u64,
}

impl Default for ExponentialBaseline {
    fn default() -> Self {
        Self::new(20)
    }
}

// ---------------------------------------------------------------------------
// DriftDetector (existing, unchanged)
// ---------------------------------------------------------------------------

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

    // -----------------------------------------------------------------------
    // ExponentialBaseline tests
    // -----------------------------------------------------------------------

    #[test]
    fn ema_seeds_on_first_value() {
        let mut ema = ExponentialBaseline::new(20);
        ema.update(42.0);
        assert_eq!(ema.mean(), 42.0);
        assert_eq!(ema.sample_count(), 1);
    }

    #[test]
    fn ema_converges_to_constant_series() {
        let mut ema = ExponentialBaseline::new(10);
        for _ in 0..100 {
            ema.update(50.0);
        }
        let (mean, stddev, confidence) = ema.stats();
        assert!((mean - 50.0).abs() < 0.001, "mean should converge to 50");
        assert!(
            stddev < 0.001,
            "stddev should be near 0 for constant series"
        );
        assert!(
            confidence > 0.99,
            "confidence should be near 1 after 100 samples"
        );
    }

    #[test]
    fn ema_is_not_warmed_up_initially() {
        let mut ema = ExponentialBaseline::new(20);
        assert!(!ema.is_warmed_up());
        // Need at least period/2 = 10 samples
        for _ in 0..9 {
            ema.update(1.0);
        }
        assert!(!ema.is_warmed_up());
        ema.update(1.0);
        assert!(ema.is_warmed_up());
    }

    #[test]
    fn ema_detects_drift_after_warmup() {
        let mut ema = ExponentialBaseline::new(10);
        // Warm up with values oscillating 90..110 so stddev > 0
        for i in 0..60 {
            ema.update(if i % 2 == 0 { 90.0 } else { 110.0 });
        }
        assert!(ema.is_warmed_up());
        let (mean, stddev, _) = ema.stats();
        assert!(
            stddev > 0.0,
            "stddev should be >0 after alternating series, got {stddev}"
        );
        // A value 5 stddevs away should always register as drift
        assert!(
            ema.is_drift(mean + 5.0 * stddev, 2.0),
            "5σ spike should be drift"
        );
        // A value within 0.5 stddev should not
        assert!(
            !ema.is_drift(mean + 0.5 * stddev, 2.0),
            "0.5σ should not be drift"
        );
    }

    #[test]
    fn ema_no_drift_before_warmup() {
        let mut ema = ExponentialBaseline::new(20);
        ema.update(100.0);
        // Only 1 sample — not warmed up, no drift reported regardless of value
        assert!(!ema.is_drift(9_000.0, 2.0));
    }

    #[test]
    fn ema_confidence_grows_with_samples() {
        let mut ema = ExponentialBaseline::new(20);
        let (_, _, c0) = ema.stats();
        assert_eq!(c0, 0.0);

        for _ in 0..20 {
            ema.update(1.0);
        }
        let (_, _, c20) = ema.stats();
        // After 1×period samples confidence ≈ 0.63
        assert!(c20 > 0.5 && c20 < 0.9, "c20={c20}");

        for _ in 0..40 {
            ema.update(1.0);
        }
        let (_, _, c60) = ema.stats();
        // After 3×period samples confidence ≈ 0.95
        assert!(c60 > 0.9, "c60={c60}");
    }
}
