//! Common metrics definitions for LiminalQA
//!
//! This module provides shared metric types and helpers used across
//! all LiminalQA components.

use prometheus_client::encoding::text::encode;
use prometheus_client::metrics::counter::Counter;
use prometheus_client::metrics::family::Family;
use prometheus_client::metrics::gauge::Gauge;
use prometheus_client::metrics::histogram::{exponential_buckets, Histogram};
use prometheus_client::registry::Registry;
use std::sync::Arc;

/// Labels for test metrics
#[derive(Clone, Debug, Hash, PartialEq, Eq, prometheus_client::encoding::EncodeLabelSet)]
pub struct TestLabels {
    pub test_type: String,
    pub status: String,
}

/// Global metrics registry for LiminalQA
pub struct MetricsRegistry {
    registry: Registry,

    // Test execution metrics
    pub tests_total: Family<TestLabels, Counter>,
    pub tests_passed: Family<TestLabels, Counter>,
    pub tests_failed: Family<TestLabels, Counter>,
    pub test_duration: Family<TestLabels, Histogram>,

    // System metrics
    pub active_tests: Gauge,
    pub total_findings: Counter,
}

impl MetricsRegistry {
    /// Create a new metrics registry with all standard metrics
    pub fn new() -> Self {
        let mut registry = Registry::default();

        // Test counters
        let tests_total = Family::<TestLabels, Counter>::default();
        registry.register(
            "liminalqa_tests_total",
            "Total number of tests executed",
            tests_total.clone(),
        );

        let tests_passed = Family::<TestLabels, Counter>::default();
        registry.register(
            "liminalqa_tests_passed_total",
            "Total number of tests passed",
            tests_passed.clone(),
        );

        let tests_failed = Family::<TestLabels, Counter>::default();
        registry.register(
            "liminalqa_test_failures_total",
            "Total number of tests failed",
            tests_failed.clone(),
        );

        // Test duration histogram
        let test_duration = Family::<TestLabels, Histogram>::new_with_constructor(|| {
            Histogram::new(exponential_buckets(0.001, 2.0, 15))
        });
        registry.register(
            "liminalqa_test_duration_seconds",
            "Test execution duration in seconds",
            test_duration.clone(),
        );

        // Gauges
        let active_tests = Gauge::default();
        registry.register(
            "liminalqa_active_tests",
            "Number of currently running tests",
            active_tests.clone(),
        );

        let total_findings = Counter::default();
        registry.register(
            "liminalqa_findings_total",
            "Total number of QA findings discovered",
            total_findings.clone(),
        );

        Self {
            registry,
            tests_total,
            tests_passed,
            tests_failed,
            test_duration,
            active_tests,
            total_findings,
        }
    }

    /// Export metrics in Prometheus text format
    pub fn export(&self) -> String {
        let mut buffer = String::new();
        encode(&mut buffer, &self.registry).unwrap();
        buffer
    }
}

impl Default for MetricsRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Shared global metrics instance
pub type SharedMetrics = Arc<MetricsRegistry>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metrics_creation() {
        let metrics = MetricsRegistry::new();

        // Increment some metrics
        metrics.tests_total.get_or_create(&TestLabels {
            test_type: "unit".to_string(),
            status: "success".to_string(),
        }).inc();

        metrics.active_tests.set(5);

        // Export and verify format
        let output = metrics.export();
        assert!(output.contains("liminalqa_tests_total"));
        assert!(output.contains("liminalqa_active_tests"));
    }
}
