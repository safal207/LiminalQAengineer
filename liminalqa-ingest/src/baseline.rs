use liminalqa_core::{
    baseline::DriftDetector,
    entities::Test,
    metrics::{BaselineLabels, SharedMetrics},
};
use liminalqa_db::LiminalDB;
use tracing::{info, warn};

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

    let durations: Vec<f64> = history.iter().map(|t| t.duration_ms as f64).collect();

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
