use crate::{
    resonance::{stability_score, FlakeDetector},
    types::TestStatus,
};

// ---------------------------------------------------------------------------
// Triage result
// ---------------------------------------------------------------------------

/// Classification produced by `TriageEngine` for a single test's run history.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TriageVerdict {
    /// The test has started failing recently and was stable before — likely a
    /// real regression introduced by recent changes.
    NewBug,
    /// The test was already known to be flaky (oscillates pass/fail) and the
    /// current failure fits that pattern.
    Flake,
    /// A previously stable-failing test; it was already categorised and tracked.
    KnownIssue,
    /// The test is passing consistently — no action required.
    Stable,
}

impl std::fmt::Display for TriageVerdict {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TriageVerdict::NewBug => write!(f, "new_bug"),
            TriageVerdict::Flake => write!(f, "flake"),
            TriageVerdict::KnownIssue => write!(f, "known_issue"),
            TriageVerdict::Stable => write!(f, "stable"),
        }
    }
}

// ---------------------------------------------------------------------------
// Triage engine
// ---------------------------------------------------------------------------

/// Classifies a test's health based on its run history.
///
/// ## Algorithm
///
/// Given a slice of `TestStatus` values (newest-last):
///
/// 1. **Stable** — all recent runs pass and stability ≥ threshold.
/// 2. **Flake** — `FlakeDetector` detects oscillation *or* stability < `stability_threshold`.
/// 3. **NewBug** — the last `recent_window` runs are all failures, but the
///    earlier portion of the history has a stability ≥ `stable_history_threshold`,
///    suggesting a recent regression.
/// 4. **KnownIssue** — everything else: persistent failures without the
///    clear oscillation signature of a flake.
pub struct TriageEngine {
    detector: FlakeDetector,
    /// Stability below this triggers flake / new-bug analysis (default 0.9).
    stability_threshold: f64,
    /// Minimum history length before non-Stable verdicts are issued (default 3).
    min_runs: usize,
    /// Number of most-recent runs to examine for "all failing" check (default 3).
    recent_window: usize,
    /// Stability of the *older* portion required to call it a NewBug (default 0.8).
    stable_history_threshold: f64,
}

impl Default for TriageEngine {
    fn default() -> Self {
        Self {
            detector: FlakeDetector::default(),
            stability_threshold: 0.9,
            min_runs: 3,
            recent_window: 3,
            stable_history_threshold: 0.8,
        }
    }
}

impl TriageEngine {
    pub fn new(
        flake_window: usize,
        flake_threshold: f64,
        stability_threshold: f64,
        min_runs: usize,
        recent_window: usize,
        stable_history_threshold: f64,
    ) -> Self {
        Self {
            detector: FlakeDetector::new(flake_window, flake_threshold),
            stability_threshold,
            min_runs,
            recent_window,
            stable_history_threshold,
        }
    }

    /// Classify `history` (oldest first, newest last).
    pub fn classify(&self, history: &[TestStatus]) -> TriageVerdict {
        if history.len() < self.min_runs {
            // Not enough data — assume stable until we know better
            return TriageVerdict::Stable;
        }

        let stab = stability_score(history);

        // Fast-path: everything is passing
        if stab >= self.stability_threshold && !self.detector.is_flaky(history) {
            return TriageVerdict::Stable;
        }

        // Oscillating pattern → Flake
        if self.detector.is_flaky(history) {
            return TriageVerdict::Flake;
        }

        // Check for NewBug: recent window all fail, but older history was stable
        let recent = &history[history.len().saturating_sub(self.recent_window)..];
        let recent_all_fail = recent
            .iter()
            .all(|s| matches!(s, TestStatus::Fail | TestStatus::Timeout));

        if recent_all_fail && history.len() > self.recent_window {
            let older = &history[..history.len() - self.recent_window];
            let older_stab = stability_score(older);
            if older_stab >= self.stable_history_threshold {
                return TriageVerdict::NewBug;
            }
        }

        // Persistent failure without oscillation or recent regression → KnownIssue
        TriageVerdict::KnownIssue
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn passes(n: usize) -> Vec<TestStatus> {
        vec![TestStatus::Pass; n]
    }
    fn fails(n: usize) -> Vec<TestStatus> {
        vec![TestStatus::Fail; n]
    }

    #[test]
    fn stable_all_pass() {
        let engine = TriageEngine::default();
        assert_eq!(engine.classify(&passes(10)), TriageVerdict::Stable);
    }

    #[test]
    fn flake_oscillating() {
        let engine = TriageEngine::default();
        let mut history = vec![];
        for i in 0..10 {
            history.push(if i % 2 == 0 {
                TestStatus::Pass
            } else {
                TestStatus::Fail
            });
        }
        assert_eq!(engine.classify(&history), TriageVerdict::Flake);
    }

    #[test]
    fn new_bug_recent_regressions() {
        let engine = TriageEngine::default();
        // 7 passes followed by 3 fails → NewBug
        let mut history = passes(7);
        history.extend(fails(3));
        assert_eq!(engine.classify(&history), TriageVerdict::NewBug);
    }

    #[test]
    fn known_issue_persistent_failures() {
        let engine = TriageEngine::default();
        // All 10 failures, no oscillation, no recent regression
        assert_eq!(engine.classify(&fails(10)), TriageVerdict::KnownIssue);
    }

    #[test]
    fn not_enough_data_returns_stable() {
        let engine = TriageEngine::default();
        assert_eq!(
            engine.classify(&[TestStatus::Fail, TestStatus::Fail]),
            TriageVerdict::Stable
        );
    }
}
