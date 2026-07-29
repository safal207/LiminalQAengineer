//! Strict suite-level aggregation for [`TestDecision`] values.
//!
//! The legacy `DecisionEngine::evaluate_suite` reconstructs the suite policy from
//! selected verdict categories. That can lose a test-level `AllowWithWarning`
//! produced by a non-flaky known issue. This module preserves the worst explicit
//! policy emitted by every constituent decision.

use crate::decision::{
    ActionItem, MergePolicy, RecommendedAction, SuiteDecision, SuiteSummary, TestDecision,
};
use chrono::Utc;

fn policy_rank(policy: &MergePolicy) -> u8 {
    match policy {
        MergePolicy::Unknown => 0,
        MergePolicy::Allow => 1,
        MergePolicy::AllowWithWarning => 2,
        MergePolicy::BlockSoft => 3,
        MergePolicy::Block => 4,
    }
}

/// Aggregate test decisions without discarding an explicit test-level warning.
///
/// This function is intentionally separate from the legacy aggregator so callers
/// can adopt the corrected semantics without a breaking API change.
pub fn evaluate_suite_strict(suite: &str, decisions: &[TestDecision]) -> SuiteDecision {
    let total = decisions.len();
    let blocking = decisions
        .iter()
        .filter(|decision| decision.merge_policy == MergePolicy::Block)
        .count();
    let soft_blocking = decisions
        .iter()
        .filter(|decision| decision.merge_policy == MergePolicy::BlockSoft)
        .count();
    let warning = decisions
        .iter()
        .filter(|decision| decision.merge_policy == MergePolicy::AllowWithWarning)
        .count();
    let flaky = decisions
        .iter()
        .filter(|decision| decision.verdict == "flake")
        .count();
    let degrading = decisions
        .iter()
        .filter(|decision| decision.signals.trend_direction == "degrading")
        .count();
    let skippable = decisions
        .iter()
        .filter(|decision| decision.recommended_action == RecommendedAction::Skip)
        .count();
    let stable = decisions
        .iter()
        .filter(|decision| decision.verdict == "stable")
        .count();

    let merge_policy = decisions
        .iter()
        .map(|decision| decision.merge_policy.clone())
        .max_by_key(policy_rank)
        .unwrap_or(MergePolicy::Unknown);

    let block_reason = match &merge_policy {
        MergePolicy::Block => {
            let names: Vec<&str> = decisions
                .iter()
                .filter(|decision| decision.merge_policy == MergePolicy::Block)
                .map(|decision| decision.name.as_str())
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
            let other_warnings = warning.saturating_sub(flaky.max(degrading));
            if other_warnings > 0 {
                parts.push(format!("{} warning test(s)", other_warnings));
            }
            if parts.is_empty() {
                parts.push(format!("{} warning test(s)", warning));
            }
            parts.join("; ")
        }
        MergePolicy::Unknown => "Insufficient evidence to determine merge safety".to_string(),
        MergePolicy::Allow => String::new(),
    };

    let confidence = if decisions.is_empty() {
        0.0
    } else {
        decisions
            .iter()
            .map(|decision| decision.confidence)
            .sum::<f64>()
            / decisions.len() as f64
    };

    let action_items = decisions
        .iter()
        .filter(|decision| {
            !matches!(
                decision.recommended_action,
                RecommendedAction::Skip | RecommendedAction::Run
            )
        })
        .map(|decision| ActionItem {
            name: decision.name.clone(),
            action: decision.recommended_action.clone(),
            reason: decision
                .root_cause_hints
                .first()
                .cloned()
                .unwrap_or_default(),
            severity: decision.severity.clone(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        decision::{DecisionEngine, TestSignals},
        triage::TriageVerdict,
    };

    fn decision(verdict: TriageVerdict, stability: f64, run_count: usize) -> TestDecision {
        DecisionEngine::evaluate_test(TestSignals {
            name: "test/name",
            suite: "suite",
            verdict,
            stability,
            flake_probability: 0.1,
            flake_score: 0.0,
            trend: None,
            baseline: None,
            run_count,
        })
    }

    #[test]
    fn preserves_known_issue_warning_at_suite_level() {
        let warning = decision(TriageVerdict::KnownIssue, 0.5, 10);
        assert_eq!(warning.merge_policy, MergePolicy::AllowWithWarning);

        let suite = evaluate_suite_strict("known-issue", &[warning]);
        assert_eq!(suite.merge_policy, MergePolicy::AllowWithWarning);
        assert!(suite.block_reason.contains("warning"));
        assert_eq!(suite.action_items.len(), 1);
    }

    #[test]
    fn preserves_worst_explicit_policy() {
        let stable = decision(TriageVerdict::Stable, 1.0, 20);
        let warning = decision(TriageVerdict::KnownIssue, 0.5, 10);
        let block = decision(TriageVerdict::NewBug, 0.9, 10);

        let suite = evaluate_suite_strict("mixed", &[stable, warning, block]);
        assert_eq!(suite.merge_policy, MergePolicy::Block);
    }

    #[test]
    fn empty_suite_is_unknown() {
        let suite = evaluate_suite_strict("empty", &[]);
        assert_eq!(suite.merge_policy, MergePolicy::Unknown);
        assert!(suite.block_reason.contains("Insufficient"));
    }
}
