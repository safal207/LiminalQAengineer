//! Inner Council — Signal reconciliation and unified view

use liminalqa_core::{entities::Signal, types::SignalType};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::debug;

/// Inner Council reconciles signals from multiple sources
#[derive(Debug, Clone)]
pub struct InnerCouncil {
    signals: Vec<Signal>,
}

impl InnerCouncil {
    pub fn new() -> Self {
        Self {
            signals: Vec::new(),
        }
    }

    /// Record a signal
    pub fn record(&mut self, signal: Signal) {
        debug!("Recording signal: type={:?}, timestamp={}",
               signal.signal_type, signal.timestamp);
        self.signals.push(signal);
    }

    /// Get all signals
    pub fn signals(&self) -> &[Signal] {
        &self.signals
    }

    /// Reconcile signals into a unified view
    pub fn reconcile(&self) -> ReconciliationResult {
        let mut by_type: HashMap<SignalType, Vec<&Signal>> = HashMap::new();

        for signal in &self.signals {
            by_type.entry(signal.signal_type)
                .or_default()
                .push(signal);
        }

        let mut inconsistencies = Vec::new();
        let mut patterns = Vec::new();

        // Check for timing inconsistencies
        if let Some(ui_signals) = by_type.get(&SignalType::UI) {
            if let Some(api_signals) = by_type.get(&SignalType::API) {
                // Look for UI changes without corresponding API calls
                for ui_sig in ui_signals {
                    let has_corresponding_api = api_signals.iter().any(|api_sig| {
                        (ui_sig.timestamp - api_sig.timestamp).num_milliseconds().abs() < 1000
                    });

                    if !has_corresponding_api {
                        inconsistencies.push(format!(
                            "UI signal at {} has no corresponding API signal",
                            ui_sig.timestamp
                        ));
                    }
                }
            }
        }

        // Detect latency patterns
        for signals in by_type.values() {
            if signals.len() > 1 {
                let latencies: Vec<u64> = signals
                    .iter()
                    .filter_map(|s| s.latency_ms)
                    .collect();

                if !latencies.is_empty() {
                    let avg = latencies.iter().sum::<u64>() / latencies.len() as u64;
                    let max = *latencies.iter().max().unwrap();

                    if max > avg * 3 {
                        patterns.push(format!(
                            "Latency spike detected: max={}ms, avg={}ms",
                            max, avg
                        ));
                    }
                }
            }
        }

        ReconciliationResult {
            total_signals: self.signals.len(),
            by_type: by_type.iter().map(|(k, v)| (*k, v.len())).collect(),
            inconsistencies,
            patterns,
        }
    }
}

impl Default for InnerCouncil {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReconciliationResult {
    pub total_signals: usize,
    pub by_type: HashMap<SignalType, usize>,
    pub inconsistencies: Vec<String>,
    pub patterns: Vec<String>,
}
