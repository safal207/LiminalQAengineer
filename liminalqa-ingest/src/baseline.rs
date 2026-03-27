use liminalqa_core::{
    baseline::{DriftDetector, NoiseFilter},
    entities::Test,
    metrics::{BaselineLabels, SharedMetrics},
};
use liminalqa_db::LiminalDB;
use tracing::{info, warn};

/// Update the EMA baseline for this test and return whether EMA drift was
/// detected (warmed-up baseline and current duration > 2σ from EMA mean).
/// Also updates the duration trend regression state.
pub fn update_ema_and_check_drift(db: &LiminalDB, test: &Test) -> bool {
    let duration = test.duration_ms as f64;
    if let Err(e) = db.update_ema_baseline(&test.name, &test.suite, duration) {
        warn!("Failed to update EMA for {}: {}", test.name, e);
        return false;
    }
    if let Err(e) = db.update_duration_trend(&test.name, &test.suite, duration) {
        warn!("Failed to update trend for {}: {}", test.name, e);
    }
    match db.get_ema_baseline(&test.name, &test.suite) {
        Ok(Some(baseline)) => baseline.is_drift(duration, 2.0),
        Ok(None) => false,
        Err(e) => {
            warn!("Failed to read EMA for {}: {}", test.name, e);
            false
        }
    }
}

pub fn check_baseline_drift(db: &LiminalDB, metrics: &SharedMetrics, test: &Test) {
    // 1. Get history (durations)
    // We need enough samples for meaningful stats. e.g. 50?
    let history = match db.get_test_history(&test.name, &test.suite, 50) {
        Ok(h) => h,
        Err(e) => {
            warn!("Failed to get history for baseline {}: {}", test.name, e);
            return;
        }
    };

    if history.is_empty() {
        return;
    }

    let raw_durations: Vec<f64> = history.iter().map(|t| t.duration_ms as f64).collect();

    // Filter load-induced spikes before computing baseline statistics.
    // Z-score threshold 3.0: values more than 3 σ from the mean are dropped.
    let durations = NoiseFilter::filter_zscore(&raw_durations, 3.0);

    // 2. Calculate Stats
    let detector = DriftDetector::default();
    let (mean, stddev) = detector.calculate_stats(&durations);

    // 3. Update Metrics
    let labels = BaselineLabels {
        name: test.name.clone(),
        suite: test.suite.clone(),
    };

    // prometheus_client Gauge uses i64 (AtomicI64). We use milliseconds.
    metrics
        .baseline_duration_mean
        .get_or_create(&labels)
        .set(mean as i64);

    metrics
        .baseline_duration_stddev
        .get_or_create(&labels)
        .set(stddev as i64);

    // 4. Check Drift (logging only, Prometheus handles alerts)
    let current_duration = test.duration_ms as f64;

    if detector.is_drift(current_duration, mean, stddev) {
        info!(
            "Drift detected for test {} (Duration: {}ms, Mean: {:.1}ms, StdDev: {:.1}ms)",
            test.name, current_duration, mean, stddev
        );
    }
}
