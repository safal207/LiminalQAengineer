//! Metrics collection for the test runner

use liminalqa_core::metrics::{SharedMetrics, TestLabels};
use std::time::Instant;

/// Metrics helper for tracking test execution
pub struct TestMetrics {
    metrics: SharedMetrics,
    start_time: Instant,
    test_type: String,
}

impl TestMetrics {
    /// Create a new test metrics tracker
    pub fn new(metrics: SharedMetrics, test_type: String) -> Self {
        // Increment active tests
        metrics.active_tests.inc();

        Self {
            metrics,
            start_time: Instant::now(),
            test_type,
        }
    }

    /// Record a successful test completion
    pub fn record_success(self) {
        let duration = self.start_time.elapsed();

        let labels = TestLabels {
            test_type: self.test_type.clone(),
            status: "success".to_string(),
        };

        self.metrics.tests_total.get_or_create(&labels).inc();
        self.metrics.tests_passed.get_or_create(&labels).inc();
        self.metrics
            .test_duration
            .get_or_create(&labels)
            .observe(duration.as_secs_f64());

        self.metrics.active_tests.dec();
    }

    /// Record a failed test
    pub fn record_failure(self, _error: &str) {
        let duration = self.start_time.elapsed();

        let labels = TestLabels {
            test_type: self.test_type.clone(),
            status: "failure".to_string(),
        };

        self.metrics.tests_total.get_or_create(&labels).inc();
        self.metrics.tests_failed.get_or_create(&labels).inc();
        self.metrics
            .test_duration
            .get_or_create(&labels)
            .observe(duration.as_secs_f64());

        self.metrics.active_tests.dec();
    }

    /// Record a finding/issue discovered
    pub fn record_finding(&self) {
        self.metrics.total_findings.inc();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use liminalqa_core::metrics::MetricsRegistry;
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn test_metrics_tracking() {
        let metrics = Arc::new(MetricsRegistry::new());

        // Simulate successful test
        {
            let tracker = TestMetrics::new(metrics.clone(), "integration".to_string());
            thread::sleep(Duration::from_millis(10));
            tracker.record_success();
        }

        // Verify metrics
        let output = metrics.export();
        assert!(output.contains("liminalqa_tests_total"));
        assert!(output.contains("integration"));
    }
}
