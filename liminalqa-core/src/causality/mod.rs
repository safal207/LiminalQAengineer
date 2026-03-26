//! Multi-hop weighted causality walk.
//!
//! Signals are linked causally when one precedes another within a temporal
//! window and both share the same run context. This module provides:
//!
//! * [`CausalEdge`]        — a directed causal link between two signals with a
//!   strength score.
//! * [`CausalNode`]        — a signal annotated with its depth in the chain and
//!   its accumulated causal weight.
//! * [`CausalChain`]       — the result of a multi-hop walk from a root signal.
//! * [`CausalityWalker`]   — performs the walk over a flat slice of signals.
//!
//! ## Algorithm
//!
//! 1. Start from a *root* signal (e.g. the first failing API call in a run).
//! 2. Find all signals that occurred within `window_ms` *after* the root.
//! 3. For each candidate compute an edge strength:
//!    `strength = base_importance(candidate) × time_decay(delta_ms)`
//!    where `time_decay = exp(−delta_ms / half_life_ms)`.
//! 4. Keep only candidates with strength ≥ `min_strength`.
//! 5. Recurse up to `max_depth` hops, tracking visited signal ids to avoid
//!    cycles in looping trace scenarios.
//!
//! The result is a tree (flattened to a `Vec<CausalNode>` sorted by depth
//! then descending strength) suitable for JSON serialisation.

use crate::{entities::Signal, resonance::SignalImportance, types::EntityId};
use chrono::Duration;
use serde::Serialize;
use std::collections::HashSet;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// A directed causal edge from one signal to the next.
#[derive(Debug, Clone, Serialize)]
pub struct CausalEdge {
    pub from_signal_id: String,
    pub to_signal_id: String,
    /// Time delta between the two signals in milliseconds.
    pub delta_ms: i64,
    /// Causal strength: 0.0–∞ (higher = more likely causal).
    pub strength: f64,
}

/// A signal node in the causal chain.
#[derive(Debug, Clone, Serialize)]
pub struct CausalNode {
    pub signal_id: String,
    pub signal_type: String,
    pub latency_ms: Option<u64>,
    pub timestamp: String,
    /// Hop distance from the root signal.
    pub depth: usize,
    /// Base importance (type × latency factor).
    pub base_importance: f64,
    /// Accumulated causal weight along the path from root.
    pub causal_weight: f64,
    /// Edges from this node to its successors.
    pub edges: Vec<CausalEdge>,
}

/// Result of a multi-hop causality walk starting from a root signal.
#[derive(Debug, Clone, Serialize)]
pub struct CausalChain {
    pub root_signal_id: String,
    /// All nodes reachable from the root, sorted by depth then desc weight.
    pub nodes: Vec<CausalNode>,
    /// Total number of causal hops explored.
    pub total_hops: usize,
    /// Max depth reached.
    pub max_depth_reached: usize,
}

// ---------------------------------------------------------------------------
// Walker
// ---------------------------------------------------------------------------

/// Configuration for the causality walk.
pub struct CausalityWalker {
    /// Maximum number of hops to follow from the root (default 4).
    pub max_depth: usize,
    /// Temporal window: a signal is a candidate successor if it starts within
    /// this many milliseconds *after* the current node (default 5 000 ms).
    pub window_ms: i64,
    /// Exponential decay half-life in milliseconds (default 1 000 ms).
    /// Closer successors get higher strength.
    pub half_life_ms: f64,
    /// Minimum edge strength to include a node (default 0.05).
    pub min_strength: f64,
}

impl Default for CausalityWalker {
    fn default() -> Self {
        Self {
            max_depth: 4,
            window_ms: 5_000,
            half_life_ms: 1_000.0,
            min_strength: 0.05,
        }
    }
}

// Internal state passed through the recursive walk — avoids exceeding the
// clippy `too_many_arguments` limit on `recurse`.
struct WalkState<'a> {
    all_signals: &'a [Signal],
    visited: &'a mut HashSet<EntityId>,
    out: &'a mut Vec<CausalNode>,
    max_depth: &'a mut usize,
    total_hops: &'a mut usize,
}

impl CausalityWalker {
    /// Walk from `root_id` through `signals`, returning a [`CausalChain`].
    ///
    /// `signals` must be the complete slice for the run (order does not matter).
    pub fn walk(&self, root_id: EntityId, signals: &[Signal]) -> Option<CausalChain> {
        let root = signals.iter().find(|s| s.id == root_id)?;

        let mut visited: HashSet<EntityId> = HashSet::new();
        visited.insert(root_id);

        let mut nodes: Vec<CausalNode> = Vec::new();
        let mut max_depth_reached = 0usize;
        let mut total_hops = 0usize;

        let mut state = WalkState {
            all_signals: signals,
            visited: &mut visited,
            out: &mut nodes,
            max_depth: &mut max_depth_reached,
            total_hops: &mut total_hops,
        };
        self.recurse(root, 0, 1.0, &mut state);

        Some(CausalChain {
            root_signal_id: root_id.to_string(),
            nodes,
            total_hops,
            max_depth_reached,
        })
    }

    fn recurse(&self, current: &Signal, depth: usize, parent_weight: f64, state: &mut WalkState) {
        if depth >= self.max_depth {
            return;
        }

        let base_importance = SignalImportance::compute(current);

        let mut edges: Vec<CausalEdge> = Vec::new();
        let mut successors: Vec<(&Signal, f64)> = Vec::new();

        for candidate in state.all_signals {
            if state.visited.contains(&candidate.id) {
                continue;
            }
            let delta = (candidate.timestamp - current.timestamp)
                .to_std()
                .map(|d| d.as_millis() as i64)
                .unwrap_or(-1);

            if delta <= 0 || delta > self.window_ms {
                continue;
            }

            let decay = (-delta as f64 / self.half_life_ms).exp();
            let strength = SignalImportance::compute(candidate) * decay;

            if strength < self.min_strength {
                continue;
            }

            edges.push(CausalEdge {
                from_signal_id: current.id.to_string(),
                to_signal_id: candidate.id.to_string(),
                delta_ms: delta,
                strength,
            });
            successors.push((candidate, strength));
        }

        // Sort successors by descending strength
        successors.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let node = CausalNode {
            signal_id: current.id.to_string(),
            signal_type: format!("{:?}", current.signal_type),
            latency_ms: current.latency_ms,
            timestamp: current.timestamp.to_rfc3339(),
            depth,
            base_importance,
            causal_weight: parent_weight * base_importance,
            edges,
        };
        state.out.push(node);
        *state.max_depth = (*state.max_depth).max(depth);

        for (successor, strength) in successors {
            if state.visited.contains(&successor.id) {
                continue;
            }
            state.visited.insert(successor.id);
            *state.total_hops += 1;
            self.recurse(successor, depth + 1, parent_weight * strength, state);
        }
    }
}

// ---------------------------------------------------------------------------
// Convenience: total temporal span of a walk as a `chrono::Duration`
// ---------------------------------------------------------------------------

/// Maximum temporal window as a `chrono::Duration` for use in DB queries.
pub fn window_duration(walker: &CausalityWalker) -> Duration {
    Duration::milliseconds(walker.window_ms * walker.max_depth as i64)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::disallowed_methods)]
mod tests {
    use super::*;
    use crate::{
        entities::Signal,
        temporal::BiTemporalTime,
        types::{EntityId, SignalType},
    };
    use chrono::{TimeZone, Utc};
    use std::collections::HashMap;

    fn make_signal(
        run_id: EntityId,
        signal_type: SignalType,
        at_ms: i64,
        latency: Option<u64>,
    ) -> Signal {
        Signal {
            id: EntityId::new(),
            run_id,
            test_id: EntityId::new(),
            signal_type,
            latency_ms: latency,
            timestamp: Utc.timestamp_millis_opt(at_ms).unwrap(),
            payload_ref: None,
            metadata: HashMap::new(),
            created_at: BiTemporalTime::now(),
        }
    }

    #[test]
    fn single_hop_chain() {
        let run_id = EntityId::new();
        let root = make_signal(run_id, SignalType::API, 1_000_000, Some(200));
        let successor = make_signal(run_id, SignalType::Database, 1_001_000, Some(150));
        let root_id = root.id;
        let signals = vec![root, successor];

        let walker = CausalityWalker::default();
        let chain = walker.walk(root_id, &signals).unwrap();

        assert_eq!(chain.root_signal_id, root_id.to_string());
        assert_eq!(chain.total_hops, 1);
        assert!(!chain.nodes.is_empty());
    }

    #[test]
    fn no_successor_outside_window() {
        let run_id = EntityId::new();
        let root = make_signal(run_id, SignalType::API, 1_000_000, Some(100));
        let far = make_signal(run_id, SignalType::Database, 1_010_000, Some(100)); // 10 s later
        let root_id = root.id;
        let signals = vec![root, far];

        let walker = CausalityWalker::default(); // window = 5 000 ms
        let chain = walker.walk(root_id, &signals).unwrap();

        assert_eq!(chain.total_hops, 0);
        assert_eq!(chain.nodes.len(), 1); // only root node
    }

    #[test]
    fn root_not_found_returns_none() {
        let run_id = EntityId::new();
        let signals = vec![make_signal(run_id, SignalType::API, 1_000_000, None)];
        let walker = CausalityWalker::default();
        let missing = EntityId::new();
        assert!(walker.walk(missing, &signals).is_none());
    }

    #[test]
    fn multi_hop_depth_limit() {
        // Build a chain of 10 signals 500 ms apart
        let run_id = EntityId::new();
        let base_ms = 1_000_000i64;
        let signals: Vec<Signal> = (0..10)
            .map(|i| make_signal(run_id, SignalType::Network, base_ms + i * 500, Some(50)))
            .collect();
        let root_id = signals[0].id;

        let walker = CausalityWalker {
            max_depth: 3,
            ..Default::default()
        };
        let chain = walker.walk(root_id, &signals).unwrap();

        // Should not exceed max_depth hops
        assert!(chain.max_depth_reached < 3);
    }
}
