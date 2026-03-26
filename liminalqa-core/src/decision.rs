//! Agent-facing decision layer — aggregates all quality signals into a single
//! structured "decision packet" optimised for machine consumption.
//!
//! # Two abstraction levels
//!
//! * **[`TestDecision`]** — judgment for one test (flake risk, trend, action, merge policy)
//! * **[`SuiteDecision`]** — aggregate judgment for a whole suite / PR
//!
//! # Designed for
//! * GitHub Action bots (check `merge_policy` field)
//! * PR comment bots (render `root_cause_hints`)
//! * OpenAI / Anthropic tool calling (`TestDecision` serialises to clean JSON)
//! * CLI consumption (`limctl decision auth/login`)

use crate::{
    baseline::{ExponentialBaseline, TrendStats},
    retry::RetryPolicy,
    triage::TriageVerdict,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Action vocabulary
// ---------------------------------------------------------------------------

/// What a CI runner or AI agent should do with this test right now.
///
/// Values form a strict vocabulary — agents can `match` on them safely.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecommendedAction {
    /// Test looks fine — run it normally.
    Run,
    /// Detected flake with low–medium probability — retry once immediately.
    RetryImmediately,
    /// High-probability flake — use exponential backoff.
    RetryWithBackoff,
    /// Consistent failure — stop retrying, escalate to a human.
    Investigate,
    /// Stable now but duration is creeping up — watch before it flakes.
    MonitorTrend,
    /// Rock-solid over many runs — safe to skip on this commit.
    Skip,
    /// Confirmed new regression — halt pipeline, block merge, alert on-call.
    BlockAndAlert,
    /// Not enough run history to decide — observe without action.
    ObserveOnly,
}

impl std::fmt::Display for RecommendedAction {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::Run => "run",
            Self::RetryImmediately => "retry_immediately",
            Self::RetryWithBackoff => "retry_with_backoff",
            Self::Investigate => "investigate",
            Self::MonitorTrend => "monitor_trend",
            Self::Skip => "skip",
            Self::BlockAndAlert => "block_and_alert",
            Self::ObserveOnly => "observe_only",
        };
        write!(f, "{s}")
    }
}

// ---------------------------------------------------------------------------
// Merge policy
// ---------------------------------------------------------------------------

/// Gate decision for CI / PR merge.
///
/// Ordered by severity: `Block > BlockSoft > AllowWithWarning > Allow > Unknown`.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MergePolicy {
    /// Allow merge — everything is healthy.
    Allow,
    /// Not enough data to decide.
    Unknown,
    /// Allow but add a warning annotation to the PR.
    AllowWithWarning,
    /// Block merge pending human review (known issue or high flake risk).
    BlockSoft,
    /// Hard block — confirmed new regression.
    Block,
}

impl std::fmt::Display for MergePolicy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::Allow => "allow",
            Self::Unknown => "unknown",
            Self::AllowWithWarning => "allow_with_warning",
            Self::BlockSoft => "block_soft",
            Self::Block => "block",
        };
        write!(f, "{s}")
    }
}

// ---------------------------------------------------------------------------
// Severity
// ---------------------------------------------------------------------------

/// Impact / severity of the detected issue.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

impl std::fmt::Display for Severity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::Low => "low",
            Self::Medium => "medium",
            Self::High => "high",
            Self::Critical => "critical",
        };
        write!(f, "{s}")
    }
}

// ---------------------------------------------------------------------------
// Signal snapshot
// ---------------------------------------------------------------------------

/// Raw numeric signals that fed the decision — useful for debugging and
/// transparency.  Agents that need only the verdict can ignore this field.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalSnapshot {
    pub stability_score: f64,
    pub flake_probability: f64,
    pub flake_score: f64,
    /// `"degrading"` | `"stable"` | `"improving"` | `"unknown"`
    pub trend_direction: String,
    pub slope_ms_per_run: Option<f64>,
    pub r_squared: Option<f64>,
    pub ema_mean_ms: Option<f64>,
    pub ema_stddev_ms: Option<f64>,
    /// EMA warmup confidence 0.0–1.0.
    pub ema_confidence: Option<f64>,
    /// Adaptive timeout derived from EMA.  `null` = baseline not warmed up.
    pub suggested_timeout_ms: Option<u64>,
    pub run_count: usize,
}

// ---------------------------------------------------------------------------
// Test-level decision
// ---------------------------------------------------------------------------

/// Structured judgment for a single test.
///
/// Optimised for machine consumption:
/// - All fields have stable names and types.
/// - `recommended_action` and `merge_policy` use a closed enum vocabulary.
/// - `root_cause_hints` is a list of plain-language strings suitable for
///   PR comment annotations or LLM context injection.
/// - `signals` provides full transparency into the computation.
///
/// ## Example (JSON)
/// ```json
/// {
///   "name": "auth/login",
///   "suite": "auth",
///   "verdict": "flake",
///   "confidence": 0.82,
///   "severity": "high",
///   "recommended_action": "retry_with_backoff",
///   "merge_policy": "allow_with_warning",
///   "retry_policy": "backoff(3 retries, 500ms→8000ms)",
///   "signals": { ... },
///   "root_cause_hints": ["Test oscillates 55% pass — timing/env sensitive"],
///   "computed_at": "2025-03-26T12:00:00Z"
/// }
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestDecision {
    pub name: String,
    pub suite: String,
    /// Triage verdict string (`"stable"` / `"flake"` / `"known_issue"` / `"new_bug"`).
    pub verdict: String,
    /// Decision confidence 0.0–1.0.  Grows as run history accumulates.
    pub confidence: f64,
    pub severity: Severity,
    pub recommended_action: RecommendedAction,
    pub merge_policy: MergePolicy,
    /// Human-readable retry policy string (empty for `skip` / `investigate`).
    pub retry_policy: String,
    /// All numeric signals that contributed to this judgment.
    pub signals: SignalSnapshot,
    /// Plain-language hints about likely root causes, suitable for PR comments.
    pub root_cause_hints: Vec<String>,
    /// ISO 8601 timestamp of computation.
    pub computed_at: String,
}

// ---------------------------------------------------------------------------
// Suite-level decision
// ---------------------------------------------------------------------------

/// Aggregate judgment for a whole suite or PR.
///
/// `merge_policy` is the *worst* policy across all constituent tests.
/// Agents should check `merge_policy` first, then iterate `action_items`
/// for tests that need human attention.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SuiteDecision {
    pub suite: String,
    /// Aggregate (worst-case) merge gate.
    pub merge_policy: MergePolicy,
    /// Human-readable explanation for a block or warning (empty if `allow`).
    pub block_reason: String,
    /// Mean confidence across all test decisions.
    pub confidence: f64,
    pub summary: SuiteSummary,
    /// Tests that require action — stable/skip tests are excluded to reduce noise.
    pub action_items: Vec<ActionItem>,
    pub computed_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SuiteSummary {
    pub total_tests: usize,
    pub blocking_failures: usize,
    pub flaky_tests: usize,
    pub stable_tests: usize,
    pub degrading_tests: usize,
    pub skippable_tests: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionItem {
    pub name: String,
    pub action: RecommendedAction,
    pub reason: String,
    pub severity: Severity,
}

// ---------------------------------------------------------------------------
// Input struct for evaluate_test
// ---------------------------------------------------------------------------

/// All signal inputs for a single test evaluation.
/// Using a struct avoids the clippy `too_many_arguments` limit.
pub struct TestSignals<'a> {
    pub name: &'a str,
    pub suite: &'a str,
    pub verdict: TriageVerdict,
    /// Pass rate 0.0–1.0.
    pub stability: f64,
    /// Composite flake risk 0.0–1.0.
    pub flake_probability: f64,
    /// Oscillation-based flake score 0.0–1.0.
    pub flake_score: f64,
    /// Optional linear-regression trend (from `DurationTrend::regression()`).
    pub trend: Option<&'a TrendStats>,
    /// Optional EMA baseline (from `ExponentialBaseline`).
    pub baseline: Option<&'a ExponentialBaseline>,
    /// Total number of historical runs available.
    pub run_count: usize,
}

// ---------------------------------------------------------------------------
// DecisionEngine
// ---------------------------------------------------------------------------

/// Stateless engine: converts raw signal values into structured decisions.
///
/// All methods are pure functions — no database access, no async.
/// The caller (HTTP handler) fetches signals and passes them in.
pub struct DecisionEngine;

impl DecisionEngine {
    /// Produce a test-level decision packet from pre-computed signal values.
    pub fn evaluate_test(s: TestSignals<'_>) -> TestDecision {
        let TestSignals {
            name,
            suite,
            verdict,
            stability,
            flake_probability,
            flake_score,
            trend,
            baseline,
            run_count,
        } = s;
        // --- confidence ---------------------------------------------------
        // Blends: depth of run history (saturates at ~30 runs) + EMA warmup
        let history_conf = (1.0 - (-(run_count as f64) / 10.0).exp()).min(1.0);
        let ema_conf = baseline.map(|b| b.stats().2).unwrap_or(0.0);
        let confidence = (0.7 * history_conf + 0.3 * ema_conf).min(1.0);

        // --- trend fields -------------------------------------------------
        let (trend_dir, slope, r_sq) = match trend {
            Some(t) => {
                let dir = if t.slope_ms_per_run > 0.5 {
                    "degrading"
                } else if t.slope_ms_per_run < -0.5 {
                    "improving"
                } else {
                    "stable"
                };
                (dir, Some(t.slope_ms_per_run), Some(t.r_squared))
            }
            None => ("unknown", None, None),
        };
        let is_degrading = trend.map(|t| t.slope_ms_per_run > 5.0).unwrap_or(false);

        // --- EMA fields ---------------------------------------------------
        let (ema_mean, ema_stddev, ema_confidence, suggested_timeout) = match baseline {
            Some(b) => {
                let (mean, stddev, conf) = b.stats();
                (Some(mean), Some(stddev), Some(conf), b.suggested_timeout_ms(3.0))
            }
            None => (None, None, None, None),
        };

        // --- core policy --------------------------------------------------
        let (action, merge_policy, severity) =
            Self::policy(&verdict, stability, flake_probability, is_degrading, run_count);

        // --- retry policy string ------------------------------------------
        let retry_policy = RetryPolicy::from_triage(&verdict, stability).describe();

        // --- root cause hints ---------------------------------------------
        let root_cause_hints =
            Self::hints(&verdict, stability, flake_probability, trend_dir, slope, run_count);

        let signals = SignalSnapshot {
            stability_score: stability,
            flake_probability,
            flake_score,
            trend_direction: trend_dir.to_string(),
            slope_ms_per_run: slope,
            r_squared: r_sq,
            ema_mean_ms: ema_mean,
            ema_stddev_ms: ema_stddev,
            ema_confidence,
            suggested_timeout_ms: suggested_timeout,
            run_count,
        };

        TestDecision {
            name: name.to_string(),
            suite: suite.to_string(),
            verdict: verdict.to_string(),
            confidence,
            severity,
            recommended_action: action,
            merge_policy,
            retry_policy,
            signals,
            root_cause_hints,
            computed_at: Utc::now().to_rfc3339(),
        }
    }

    /// Determine action, merge policy, and severity from verdict + signals.
    fn policy(
        verdict: &TriageVerdict,
        stability: f64,
        flake_probability: f64,
        is_degrading: bool,
        run_count: usize,
    ) -> (RecommendedAction, MergePolicy, Severity) {
        if run_count < 3 {
            return (
                RecommendedAction::ObserveOnly,
                MergePolicy::Unknown,
                Severity::Low,
            );
        }

        match verdict {
            TriageVerdict::NewBug => (
                RecommendedAction::BlockAndAlert,
                MergePolicy::Block,
                Severity::Critical,
            ),

            TriageVerdict::KnownIssue => (
                RecommendedAction::Investigate,
                // High-confidence known-issue = soft block (we're sure it's broken)
                if stability < 0.3 {
                    MergePolicy::BlockSoft
                } else {
                    MergePolicy::AllowWithWarning
                },
                Severity::High,
            ),

            TriageVerdict::Flake => {
                let action = if flake_probability >= 0.6 {
                    RecommendedAction::RetryWithBackoff
                } else {
                    RecommendedAction::RetryImmediately
                };
                let sev = if flake_probability >= 0.7 {
                    Severity::High
                } else {
                    Severity::Medium
                };
                (action, MergePolicy::AllowWithWarning, sev)
            }

            TriageVerdict::Stable => {
                if is_degrading {
                    (
                        RecommendedAction::MonitorTrend,
                        MergePolicy::AllowWithWarning,
                        Severity::Medium,
                    )
                } else if stability >= 0.97 {
                    (RecommendedAction::Skip, MergePolicy::Allow, Severity::Low)
                } else {
                    (RecommendedAction::Run, MergePolicy::Allow, Severity::Low)
                }
            }
        }
    }

    /// Generate plain-language root cause hints for PR comments / LLM context.
    fn hints(
        verdict: &TriageVerdict,
        stability: f64,
        flake_probability: f64,
        trend_dir: &str,
        slope: Option<f64>,
        run_count: usize,
    ) -> Vec<String> {
        let mut hints: Vec<String> = Vec::new();

        match verdict {
            TriageVerdict::NewBug => {
                hints.push(format!(
                    "Test was stable ({:.0}% pass rate) but failed in the last 3 consecutive runs — likely a real regression introduced by recent changes",
                    stability * 100.0
                ));
            }
            TriageVerdict::KnownIssue => {
                hints.push(format!(
                    "Test has been consistently failing ({:.0}% pass rate) — this is a pre-existing known issue, not caused by recent changes",
                    stability * 100.0
                ));
            }
            TriageVerdict::Flake => {
                hints.push(format!(
                    "Test oscillates between pass and fail (stability={:.0}%, flake_probability={:.0}%) — likely sensitive to timing, environment state, or test order",
                    stability * 100.0,
                    flake_probability * 100.0
                ));
                if flake_probability > 0.7 {
                    hints.push(
                        "High flake risk: consider adding retry logic, improving test isolation, or investigating shared state".into()
                    );
                }
            }
            TriageVerdict::Stable => {}
        }

        if trend_dir == "degrading" {
            if let Some(s) = slope {
                hints.push(format!(
                    "Duration trending upward at +{:.1}ms/run — projected +{:.0}ms in the next 50 runs",
                    s,
                    s * 50.0
                ));
                if s > 20.0 {
                    hints.push(
                        "Steep degradation rate — possible memory/connection leak or upstream dependency slowdown".into()
                    );
                }
            }
        }

        if run_count < 5 {
            hints.push(format!(
                "Low sample count ({} run(s)) — confidence is limited; observe more runs before taking action",
                run_count
            ));
        }

        hints
    }

    /// Aggregate multiple test decisions into a suite-level (PR-level) judgment.
    ///
    /// The suite `merge_policy` is the **worst** (highest-severity) policy
    /// across all tests.  This means a single new regression blocks the whole
    /// suite — intentional, matches standard CI gate semantics.
    pub fn evaluate_suite(suite: &str, decisions: &[TestDecision]) -> SuiteDecision {
        let total = decisions.len();

        let blocking = decisions
            .iter()
            .filter(|d| d.merge_policy == MergePolicy::Block)
            .count();
        let soft_blocking = decisions
            .iter()
            .filter(|d| d.merge_policy == MergePolicy::BlockSoft)
            .count();
        let flaky = decisions
            .iter()
            .filter(|d| d.verdict == "flake")
            .count();
        let degrading = decisions
            .iter()
            .filter(|d| d.signals.trend_direction == "degrading")
            .count();
        let skippable = decisions
            .iter()
            .filter(|d| d.recommended_action == RecommendedAction::Skip)
            .count();
        let stable = decisions
            .iter()
            .filter(|d| d.verdict == "stable")
            .count();

        // Worst-case merge policy
        let merge_policy = if blocking > 0 {
            MergePolicy::Block
        } else if soft_blocking > 0 {
            MergePolicy::BlockSoft
        } else if flaky > 0 || degrading > 0 {
            MergePolicy::AllowWithWarning
        } else if total == 0 {
            MergePolicy::Unknown
        } else {
            MergePolicy::Allow
        };

        let block_reason = match &merge_policy {
            MergePolicy::Block => {
                let names: Vec<&str> = decisions
                    .iter()
                    .filter(|d| d.merge_policy == MergePolicy::Block)
                    .map(|d| d.name.as_str())
                    .collect();
                format!("New regression detected in: {}", names.join(", "))
            }
            MergePolicy::BlockSoft => format!(
                "{} known-issue test(s) with high failure confidence — human approval required",
                soft_blocking
            ),
            MergePolicy::AllowWithWarning => {
                let mut parts = Vec::new();
                if flaky > 0 {
                    parts.push(format!("{} flaky test(s)", flaky));
                }
                if degrading > 0 {
                    parts.push(format!("{} degrading test(s)", degrading));
                }
                parts.join("; ")
            }
            _ => String::new(),
        };

        let confidence = if decisions.is_empty() {
            0.0
        } else {
            decisions.iter().map(|d| d.confidence).sum::<f64>() / decisions.len() as f64
        };

        // Only emit action items for tests that need human or agent attention
        let action_items: Vec<ActionItem> = decisions
            .iter()
            .filter(|d| {
                !matches!(
                    d.recommended_action,
                    RecommendedAction::Skip | RecommendedAction::Run
                )
            })
            .map(|d| ActionItem {
                name: d.name.clone(),
                action: d.recommended_action.clone(),
                reason: d.root_cause_hints.first().cloned().unwrap_or_default(),
                severity: d.severity.clone(),
            })
            .collect();

        SuiteDecision {
            suite: suite.to_string(),
            merge_policy,
            block_reason,
            confidence,
            summary: SuiteSummary {
                total_tests: total,
                blocking_failures: blocking,
                flaky_tests: flaky,
                stable_tests: stable,
                degrading_tests: degrading,
                skippable_tests: skippable,
            },
            action_items,
            computed_at: Utc::now().to_rfc3339(),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_decision(
        verdict: TriageVerdict,
        stability: f64,
        flake_prob: f64,
        run_count: usize,
    ) -> TestDecision {
        DecisionEngine::evaluate_test(TestSignals {
            name: "test/name",
            suite: "suite",
            verdict,
            stability,
            flake_probability: flake_prob,
            flake_score: flake_prob * 0.9,
            trend: None,
            baseline: None,
            run_count,
        })
    }

    // ── test-level ────────────────────────────────────────────────────────

    #[test]
    fn new_bug_blocks_merge_and_alerts() {
        let d = make_decision(TriageVerdict::NewBug, 0.9, 0.1, 10);
        assert_eq!(d.merge_policy, MergePolicy::Block);
        assert_eq!(d.recommended_action, RecommendedAction::BlockAndAlert);
        assert_eq!(d.severity, Severity::Critical);
        assert!(!d.root_cause_hints.is_empty());
    }

    #[test]
    fn known_issue_low_stability_soft_blocks() {
        let d = make_decision(TriageVerdict::KnownIssue, 0.1, 0.1, 10);
        assert_eq!(d.merge_policy, MergePolicy::BlockSoft);
        assert_eq!(d.recommended_action, RecommendedAction::Investigate);
        assert_eq!(d.severity, Severity::High);
    }

    #[test]
    fn known_issue_moderate_stability_warns() {
        let d = make_decision(TriageVerdict::KnownIssue, 0.5, 0.1, 10);
        assert_eq!(d.merge_policy, MergePolicy::AllowWithWarning);
        assert_eq!(d.recommended_action, RecommendedAction::Investigate);
    }

    #[test]
    fn high_probability_flake_uses_backoff() {
        let d = make_decision(TriageVerdict::Flake, 0.5, 0.75, 10);
        assert_eq!(d.recommended_action, RecommendedAction::RetryWithBackoff);
        assert_eq!(d.merge_policy, MergePolicy::AllowWithWarning);
        assert_eq!(d.severity, Severity::High);
    }

    #[test]
    fn low_probability_flake_retries_immediately() {
        let d = make_decision(TriageVerdict::Flake, 0.8, 0.3, 10);
        assert_eq!(d.recommended_action, RecommendedAction::RetryImmediately);
        assert_eq!(d.merge_policy, MergePolicy::AllowWithWarning);
        assert_eq!(d.severity, Severity::Medium);
    }

    #[test]
    fn stable_rock_solid_allows_skip() {
        let d = make_decision(TriageVerdict::Stable, 1.0, 0.0, 20);
        assert_eq!(d.recommended_action, RecommendedAction::Skip);
        assert_eq!(d.merge_policy, MergePolicy::Allow);
        assert_eq!(d.severity, Severity::Low);
    }

    #[test]
    fn stable_with_degrading_trend_warns() {
        use crate::baseline::TrendStats;
        let trend = TrendStats {
            slope_ms_per_run: 15.0, // > 5.0 threshold
            intercept_ms: 1000.0,
            r_squared: 0.9,
            sample_count: 30,
        };
        let d = DecisionEngine::evaluate_test(TestSignals {
            name: "slow/test",
            suite: "perf",
            verdict: TriageVerdict::Stable,
            stability: 1.0,
            flake_probability: 0.0,
            flake_score: 0.0,
            trend: Some(&trend),
            baseline: None,
            run_count: 20,
        });
        assert_eq!(d.recommended_action, RecommendedAction::MonitorTrend);
        assert_eq!(d.merge_policy, MergePolicy::AllowWithWarning);
        // Hints should mention the trend
        assert!(d
            .root_cause_hints
            .iter()
            .any(|h| h.contains("trending upward")));
    }

    #[test]
    fn insufficient_data_observes_only() {
        let d = make_decision(TriageVerdict::Stable, 1.0, 0.0, 2); // < 3 runs
        assert_eq!(d.recommended_action, RecommendedAction::ObserveOnly);
        assert_eq!(d.merge_policy, MergePolicy::Unknown);
    }

    #[test]
    fn confidence_grows_with_run_count() {
        let low = make_decision(TriageVerdict::Stable, 1.0, 0.0, 3);
        let high = make_decision(TriageVerdict::Stable, 1.0, 0.0, 30);
        assert!(
            low.confidence < high.confidence,
            "low={} high={}",
            low.confidence,
            high.confidence
        );
        // After 30 runs: history_conf ≈ 0.95, ema_conf = 0 (no baseline passed)
        // → confidence ≈ 0.7 × 0.95 = 0.665
        assert!(high.confidence > 0.6, "expected > 0.6, got {}", high.confidence);
    }

    // ── suite-level ───────────────────────────────────────────────────────

    fn new_bug_decision() -> TestDecision {
        make_decision(TriageVerdict::NewBug, 0.9, 0.05, 10)
    }

    fn flake_decision() -> TestDecision {
        make_decision(TriageVerdict::Flake, 0.5, 0.7, 10)
    }

    fn stable_decision() -> TestDecision {
        make_decision(TriageVerdict::Stable, 1.0, 0.0, 20)
    }

    #[test]
    fn suite_with_regression_blocks() {
        let decisions = vec![new_bug_decision(), flake_decision(), stable_decision()];
        let suite = DecisionEngine::evaluate_suite("payments", &decisions);
        assert_eq!(suite.merge_policy, MergePolicy::Block);
        assert!(suite.block_reason.contains("regression"));
        assert_eq!(suite.summary.blocking_failures, 1);
        assert_eq!(suite.summary.flaky_tests, 1);
        // Only non-run/skip tests appear in action_items
        let actions: Vec<&str> = suite.action_items.iter().map(|a| a.name.as_str()).collect();
        assert!(actions.contains(&"test/name"));
    }

    #[test]
    fn suite_all_stable_allows() {
        let decisions = vec![stable_decision(), stable_decision()];
        let suite = DecisionEngine::evaluate_suite("infra", &decisions);
        assert_eq!(suite.merge_policy, MergePolicy::Allow);
        assert!(suite.block_reason.is_empty());
        assert!(suite.action_items.is_empty());
    }

    #[test]
    fn suite_only_flakes_warns() {
        let decisions = vec![flake_decision(), stable_decision()];
        let suite = DecisionEngine::evaluate_suite("auth", &decisions);
        assert_eq!(suite.merge_policy, MergePolicy::AllowWithWarning);
        assert!(suite.block_reason.contains("flaky"));
    }

    #[test]
    fn empty_suite_returns_unknown() {
        let suite = DecisionEngine::evaluate_suite("empty", &[]);
        assert_eq!(suite.merge_policy, MergePolicy::Unknown);
        assert_eq!(suite.summary.total_tests, 0);
    }

    #[test]
    fn suite_worst_policy_wins() {
        // Mix of Block + Allow = Block overall
        let decisions = vec![new_bug_decision(), stable_decision(), stable_decision()];
        let suite = DecisionEngine::evaluate_suite("mixed", &decisions);
        assert_eq!(suite.merge_policy, MergePolicy::Block);
    }
}
