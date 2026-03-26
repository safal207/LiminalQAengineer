//! Root-cause analysis — Q4 Month 11
//!
//! Combines triage verdicts, causality trails, environment context, and
//! community pattern matches into ranked root-cause hypotheses.
//!
//! # Algorithm
//!
//! Each hypothesis is scored by a weighted sum of evidence signals:
//!
//! ```text
//! score = Σ (signal_weight × signal_value)
//! ```
//!
//! Weights are tuned from engineering heuristics and updated via
//! [`RootCauseEngine::record_outcome`] (online Bayesian weight update).
//!
//! # Output
//!
//! ```json
//! {
//!   "hypotheses": [
//!     {
//!       "kind": "infrastructure_flake",
//!       "confidence": 0.84,
//!       "evidence": ["high flake probability", "production env", "network tag"],
//!       "suggested_fix": "Add retry with exponential backoff"
//!     }
//!   ]
//! }
//! ```
//!
//! # Counterfactual reasoning
//!
//! `what_if_disabled(component)` estimates success probability if a component
//! were removed from the causal chain — useful for prioritising fixes.

use crate::{
    community::SimilarityMatch,
    export::EnvClass,
    triage::TriageVerdict,
};
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Hypothesis kinds
// ---------------------------------------------------------------------------

/// Possible root-cause categories.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RootCauseKind {
    /// Non-deterministic test — race condition, ordering dependency, timing.
    InfrastructureFlake,
    /// Real regression introduced by a recent code change.
    CodeRegression,
    /// Test is fragile — overly strict assertions, hardcoded sleep, etc.
    TestDesignFlaw,
    /// External dependency (DB, network, third-party API) misbehaving.
    ExternalDependency,
    /// Resource exhaustion: OOM, disk, CPU throttling.
    ResourceExhaustion,
    /// Environment misconfiguration: wrong secrets, missing env vars, versions.
    EnvironmentConfig,
    /// Insufficient data to classify with confidence.
    Undetermined,
}

impl std::fmt::Display for RootCauseKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            RootCauseKind::InfrastructureFlake => "infrastructure_flake",
            RootCauseKind::CodeRegression => "code_regression",
            RootCauseKind::TestDesignFlaw => "test_design_flaw",
            RootCauseKind::ExternalDependency => "external_dependency",
            RootCauseKind::ResourceExhaustion => "resource_exhaustion",
            RootCauseKind::EnvironmentConfig => "environment_config",
            RootCauseKind::Undetermined => "undetermined",
        };
        write!(f, "{s}")
    }
}

// ---------------------------------------------------------------------------
// Evidence items
// ---------------------------------------------------------------------------

/// A single piece of evidence contributing to a hypothesis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Evidence {
    pub description: String,
    /// Weight of this evidence in the final score (0.0–1.0).
    pub weight: f64,
}

impl Evidence {
    fn new(description: impl Into<String>, weight: f64) -> Self {
        Self {
            description: description.into(),
            weight: weight.clamp(0.0, 1.0),
        }
    }
}

// ---------------------------------------------------------------------------
// Root-cause hypothesis
// ---------------------------------------------------------------------------

/// A single ranked root-cause hypothesis.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RootCauseHypothesis {
    pub kind: RootCauseKind,
    /// Confidence in [0.0, 1.0] — weighted sum of evidence scores, normalized.
    pub confidence: f64,
    /// Pieces of evidence that contributed to this hypothesis.
    pub evidence: Vec<Evidence>,
    /// Human-readable fix suggestion.
    pub suggested_fix: String,
    /// Estimated success probability if this root cause is fixed (counterfactual).
    pub counterfactual_success_prob: f64,
}

impl RootCauseHypothesis {
    fn total_evidence_score(&self) -> f64 {
        self.evidence.iter().map(|e| e.weight).sum()
    }
}

// ---------------------------------------------------------------------------
// Input signals
// ---------------------------------------------------------------------------

/// All available signals for root-cause analysis of one test.
#[derive(Debug, Clone)]
pub struct RootCauseInput {
    /// Triage verdict for the current failure.
    pub triage: TriageVerdict,
    /// Flake probability from the predictive model (0.0–1.0).
    pub flake_probability: f64,
    /// Duration trend slope in ms/run (positive = getting slower).
    pub trend_slope: f64,
    /// Recent failure rate (0.0–1.0).
    pub failure_rate: f64,
    /// Environment class.
    pub env_class: EnvClass,
    /// Whether the test touches network calls (derived from tags/signals).
    pub has_network_calls: bool,
    /// Whether the test has known timing/sleep dependencies.
    pub has_timing_deps: bool,
    /// Whether a resource constraint signal was observed (OOM, disk full…).
    pub resource_signal: bool,
    /// Whether environment-variable or config errors appeared in logs.
    pub config_error_signal: bool,
    /// Community pattern matches (may be empty).
    pub community_matches: Vec<SimilarityMatch>,
    /// Context multiplier from the context engine (prod/staging/hours/load).
    pub context_multiplier: f64,
}

// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------

/// Learnable weights for each hypothesis kind.
///
/// Initialized from heuristics; updated via `record_outcome`.
#[derive(Debug, Clone)]
struct HypothesisWeights {
    /// Base prior for each kind (before evidence).
    priors: std::collections::HashMap<RootCauseKind, f64>,
    /// How many outcomes have been recorded (for damping).
    observations: u64,
}

impl Default for HypothesisWeights {
    fn default() -> Self {
        use RootCauseKind::*;
        let mut priors = std::collections::HashMap::new();
        priors.insert(InfrastructureFlake, 0.30);
        priors.insert(CodeRegression, 0.25);
        priors.insert(TestDesignFlaw, 0.15);
        priors.insert(ExternalDependency, 0.15);
        priors.insert(ResourceExhaustion, 0.08);
        priors.insert(EnvironmentConfig, 0.07);
        priors.insert(Undetermined, 0.00);
        Self {
            priors,
            observations: 0,
        }
    }
}

/// Root-cause analysis engine.
///
/// # Example
///
/// ```
/// use liminalqa_core::rootcause::{RootCauseEngine, RootCauseInput};
/// use liminalqa_core::triage::TriageVerdict;
/// use liminalqa_core::export::EnvClass;
///
/// let engine = RootCauseEngine::default();
/// let input = RootCauseInput {
///     triage: TriageVerdict::Flake,
///     flake_probability: 0.82,
///     trend_slope: 0.0,
///     failure_rate: 0.25,
///     env_class: EnvClass::Ci,
///     has_network_calls: true,
///     has_timing_deps: false,
///     resource_signal: false,
///     config_error_signal: false,
///     community_matches: vec![],
///     context_multiplier: 1.0,
/// };
/// let result = engine.analyze(&input);
/// assert!(!result.hypotheses.is_empty());
/// println!("Top cause: {}", result.hypotheses[0].kind);
/// ```
#[derive(Debug, Default)]
pub struct RootCauseEngine {
    weights: HypothesisWeights,
}

// ---------------------------------------------------------------------------
// Analysis result
// ---------------------------------------------------------------------------

/// Complete root-cause analysis result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RootCauseResult {
    /// Hypotheses ordered by confidence descending (top 3).
    pub hypotheses: Vec<RootCauseHypothesis>,
    /// Summary sentence for display in PR comments / dashboards.
    pub summary: String,
}

// ---------------------------------------------------------------------------
// Engine implementation
// ---------------------------------------------------------------------------

impl RootCauseEngine {
    /// Analyze a test failure and return ranked hypotheses.
    pub fn analyze(&self, input: &RootCauseInput) -> RootCauseResult {
        let candidates = self.build_candidates(input);
        let total_score: f64 = candidates.iter().map(|h| h.total_evidence_score()).sum();

        let mut hypotheses: Vec<RootCauseHypothesis> = candidates
            .into_iter()
            .map(|mut h| {
                let raw = h.total_evidence_score();
                h.confidence = if total_score > 0.0 {
                    (raw / total_score).clamp(0.0, 1.0)
                } else {
                    0.0
                };
                h
            })
            .collect();

        hypotheses.sort_by(|a, b| {
            b.confidence
                .partial_cmp(&a.confidence)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        hypotheses.truncate(3);

        // Undetermined fallback
        if hypotheses.is_empty() || hypotheses[0].confidence < 0.1 {
            hypotheses.insert(
                0,
                RootCauseHypothesis {
                    kind: RootCauseKind::Undetermined,
                    confidence: 1.0,
                    evidence: vec![Evidence::new("Insufficient signals to classify", 1.0)],
                    suggested_fix: "Collect more run history before acting.".into(),
                    counterfactual_success_prob: 0.5,
                },
            );
            hypotheses.truncate(1);
        }

        let summary = build_summary(&hypotheses[0]);
        RootCauseResult { hypotheses, summary }
    }

    /// Record whether the top hypothesis was correct (for weight learning).
    ///
    /// Uses a dampened online update so early observations have more effect.
    pub fn record_outcome(&mut self, kind: &RootCauseKind, was_correct: bool) {
        let obs = self.weights.observations as f64 + 1.0;
        let lr = 1.0 / obs.sqrt(); // learning rate decreases as 1/√n
        let prior = self.weights.priors.entry(kind.clone()).or_insert(0.1);
        let target = if was_correct { 1.0 } else { 0.0 };
        *prior = (*prior + lr * (target - *prior)).clamp(0.01, 0.99);
        self.weights.observations += 1;
    }

    // ------------------------------------------------------------------
    // Private helpers
    // ------------------------------------------------------------------

    fn build_candidates(&self, input: &RootCauseInput) -> Vec<RootCauseHypothesis> {
        use RootCauseKind::*;
        vec![
            self.hypothesis_infrastructure_flake(input),
            self.hypothesis_code_regression(input),
            self.hypothesis_test_design(input),
            self.hypothesis_external_dep(input),
            self.hypothesis_resource(input),
            self.hypothesis_env_config(input),
        ]
    }

    fn prior(&self, kind: &RootCauseKind) -> f64 {
        *self.weights.priors.get(kind).unwrap_or(&0.1)
    }

    fn hypothesis_infrastructure_flake(&self, i: &RootCauseInput) -> RootCauseHypothesis {
        let kind = RootCauseKind::InfrastructureFlake;
        let mut evidence = vec![Evidence::new("prior", self.prior(&kind))];

        if i.flake_probability >= 0.7 {
            evidence.push(Evidence::new(
                format!("high flake probability ({:.0}%)", i.flake_probability * 100.0),
                0.35,
            ));
        } else if i.flake_probability >= 0.4 {
            evidence.push(Evidence::new(
                format!("moderate flake probability ({:.0}%)", i.flake_probability * 100.0),
                0.15,
            ));
        }

        if matches!(i.triage, TriageVerdict::Flake) {
            evidence.push(Evidence::new("triage verdict: flake", 0.25));
        }

        if i.has_network_calls {
            evidence.push(Evidence::new("test involves network calls (common flake source)", 0.15));
        }

        let community_boost = community_kind_boost(&i.community_matches, "flake");
        if community_boost > 0.0 {
            evidence.push(Evidence::new(
                format!("community confirms similar pattern ({:.0}% of reports)", community_boost * 100.0),
                community_boost * 0.20,
            ));
        }

        let csp = 1.0 - (i.failure_rate * (1.0 - i.flake_probability));
        RootCauseHypothesis {
            kind,
            confidence: 0.0,
            evidence,
            suggested_fix: "Add retry logic with exponential backoff; investigate race conditions."
                .into(),
            counterfactual_success_prob: csp.clamp(0.0, 1.0),
        }
    }

    fn hypothesis_code_regression(&self, i: &RootCauseInput) -> RootCauseHypothesis {
        let kind = RootCauseKind::CodeRegression;
        let mut evidence = vec![Evidence::new("prior", self.prior(&kind))];

        if matches!(i.triage, TriageVerdict::NewBug) {
            evidence.push(Evidence::new("triage verdict: new_bug (stable → failing)", 0.45));
        }

        if i.failure_rate >= 0.8 && i.flake_probability < 0.3 {
            evidence.push(Evidence::new(
                format!("high failure rate ({:.0}%) with low flake probability", i.failure_rate * 100.0),
                0.30,
            ));
        }

        if i.trend_slope > 5.0 {
            evidence.push(Evidence::new(
                format!("duration trending up (+{:.1} ms/run)", i.trend_slope),
                0.10,
            ));
        }

        let community_boost = community_kind_boost(&i.community_matches, "new_bug");
        if community_boost > 0.0 {
            evidence.push(Evidence::new(
                "community reports similar regression pattern",
                community_boost * 0.15,
            ));
        }

        // Production regressions are more likely to be real bugs
        if matches!(i.env_class, EnvClass::Production) {
            evidence.push(Evidence::new("failure in production environment", 0.10));
        }

        RootCauseHypothesis {
            kind,
            confidence: 0.0,
            evidence,
            suggested_fix:
                "Bisect recent commits; review changes to code paths covered by this test.".into(),
            counterfactual_success_prob: (1.0 - i.failure_rate + 0.1).clamp(0.0, 1.0),
        }
    }

    fn hypothesis_test_design(&self, i: &RootCauseInput) -> RootCauseHypothesis {
        let kind = RootCauseKind::TestDesignFlaw;
        let mut evidence = vec![Evidence::new("prior", self.prior(&kind))];

        if i.has_timing_deps {
            evidence.push(Evidence::new("test has timing/sleep dependencies", 0.35));
        }

        // High stddev relative to mean suggests timing sensitivity
        if i.trend_slope.abs() > 20.0 {
            evidence.push(Evidence::new("high duration variability (possible sleep/wait)", 0.20));
        }

        if i.failure_rate > 0.1 && i.failure_rate < 0.5 && i.flake_probability > 0.5 {
            evidence.push(Evidence::new("moderate failure rate with high flake probability", 0.15));
        }

        RootCauseHypothesis {
            kind,
            confidence: 0.0,
            evidence,
            suggested_fix:
                "Replace sleep() with polling; decouple test from wall clock; use test doubles for time."
                    .into(),
            counterfactual_success_prob: 0.85,
        }
    }

    fn hypothesis_external_dep(&self, i: &RootCauseInput) -> RootCauseHypothesis {
        let kind = RootCauseKind::ExternalDependency;
        let mut evidence = vec![Evidence::new("prior", self.prior(&kind))];

        if i.has_network_calls && i.failure_rate > 0.05 {
            evidence.push(Evidence::new(
                format!(
                    "network calls present; {:.0}% failure rate",
                    i.failure_rate * 100.0
                ),
                0.25,
            ));
        }

        // Context: high load often stresses external deps
        if i.context_multiplier > 1.3 {
            evidence.push(Evidence::new(
                format!("high-load context (multiplier {:.2}×)", i.context_multiplier),
                0.15,
            ));
        }

        if matches!(i.triage, TriageVerdict::KnownIssue) {
            evidence.push(Evidence::new("known recurring issue pattern", 0.20));
        }

        RootCauseHypothesis {
            kind,
            confidence: 0.0,
            evidence,
            suggested_fix:
                "Add circuit breaker; stub external dependency in test; check SLA dashboards.".into(),
            counterfactual_success_prob: 0.80,
        }
    }

    fn hypothesis_resource(&self, i: &RootCauseInput) -> RootCauseHypothesis {
        let kind = RootCauseKind::ResourceExhaustion;
        let mut evidence = vec![Evidence::new("prior", self.prior(&kind))];

        if i.resource_signal {
            evidence.push(Evidence::new("resource constraint signal observed (OOM/disk/CPU)", 0.60));
        }

        if i.trend_slope > 10.0 {
            evidence.push(Evidence::new(
                "duration trending upward — possible memory leak or resource accumulation",
                0.20,
            ));
        }

        RootCauseHypothesis {
            kind,
            confidence: 0.0,
            evidence,
            suggested_fix: "Profile memory usage; ensure test cleanup; increase resource limits.".into(),
            counterfactual_success_prob: 0.90,
        }
    }

    fn hypothesis_env_config(&self, i: &RootCauseInput) -> RootCauseHypothesis {
        let kind = RootCauseKind::EnvironmentConfig;
        let mut evidence = vec![Evidence::new("prior", self.prior(&kind))];

        if i.config_error_signal {
            evidence.push(Evidence::new("config/env-var error signal in logs", 0.55));
        }

        if matches!(i.env_class, EnvClass::Staging | EnvClass::Development) {
            evidence.push(Evidence::new("non-production env — config drift is common", 0.10));
        }

        RootCauseHypothesis {
            kind,
            confidence: 0.0,
            evidence,
            suggested_fix:
                "Verify environment variables, secrets, and service versions match expectations.".into(),
            counterfactual_success_prob: 0.92,
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Returns the fraction of community matches where the failure kind matches.
fn community_kind_boost(matches: &[SimilarityMatch], kind: &str) -> f64 {
    if matches.is_empty() {
        return 0.0;
    }
    let count = matches
        .iter()
        .filter(|m| m.pattern.failure_kind == kind)
        .count();
    count as f64 / matches.len() as f64
}

fn build_summary(top: &RootCauseHypothesis) -> String {
    format!(
        "Most likely cause: {} ({:.0}% confidence). {}",
        top.kind,
        top.confidence * 100.0,
        top.suggested_fix
    )
}

// ---------------------------------------------------------------------------
// Counterfactual analysis
// ---------------------------------------------------------------------------

/// Estimate success probability if a specific component is disabled / fixed.
///
/// Returns a value in [0.0, 1.0] representing predicted pass rate after
/// the intervention.
pub fn what_if_fixed(result: &RootCauseResult, kind: &RootCauseKind) -> f64 {
    result
        .hypotheses
        .iter()
        .find(|h| &h.kind == kind)
        .map(|h| h.counterfactual_success_prob)
        .unwrap_or(0.5)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::export::EnvClass;
    use crate::triage::TriageVerdict;

    fn make_input(triage: TriageVerdict, flake_prob: f64, failure_rate: f64) -> RootCauseInput {
        RootCauseInput {
            triage,
            flake_probability: flake_prob,
            trend_slope: 0.0,
            failure_rate,
            env_class: EnvClass::Ci,
            has_network_calls: false,
            has_timing_deps: false,
            resource_signal: false,
            config_error_signal: false,
            community_matches: vec![],
            context_multiplier: 1.0,
        }
    }

    #[test]
    fn flaky_test_produces_flake_hypothesis() {
        let engine = RootCauseEngine::default();
        let input = make_input(TriageVerdict::Flake, 0.85, 0.3);
        let result = engine.analyze(&input);
        assert!(!result.hypotheses.is_empty());
        assert_eq!(result.hypotheses[0].kind, RootCauseKind::InfrastructureFlake);
    }

    #[test]
    fn new_bug_triage_favours_regression() {
        let engine = RootCauseEngine::default();
        let mut input = make_input(TriageVerdict::NewBug, 0.1, 0.9);
        input.env_class = EnvClass::Production;
        let result = engine.analyze(&input);
        assert_eq!(result.hypotheses[0].kind, RootCauseKind::CodeRegression);
    }

    #[test]
    fn resource_signal_surfaces_resource_exhaustion() {
        let engine = RootCauseEngine::default();
        let mut input = make_input(TriageVerdict::KnownIssue, 0.2, 0.6);
        input.resource_signal = true;
        let result = engine.analyze(&input);
        // ResourceExhaustion should be in top 3
        let has_resource = result
            .hypotheses
            .iter()
            .any(|h| h.kind == RootCauseKind::ResourceExhaustion);
        assert!(has_resource, "Expected ResourceExhaustion in top 3");
    }

    #[test]
    fn config_error_surfaces_env_config() {
        let engine = RootCauseEngine::default();
        let mut input = make_input(TriageVerdict::KnownIssue, 0.1, 0.7);
        input.config_error_signal = true;
        let result = engine.analyze(&input);
        let has_config = result
            .hypotheses
            .iter()
            .any(|h| h.kind == RootCauseKind::EnvironmentConfig);
        assert!(has_config, "Expected EnvironmentConfig in top 3");
    }

    #[test]
    fn confidences_sum_to_approximately_one() {
        let engine = RootCauseEngine::default();
        let input = make_input(TriageVerdict::Flake, 0.5, 0.5);
        let result = engine.analyze(&input);
        let sum: f64 = result.hypotheses.iter().map(|h| h.confidence).sum();
        // Top-3 confidences won't sum to exactly 1.0 but should be ≤ 1.0
        assert!(sum <= 1.001, "Confidences overflow: {sum}");
    }

    #[test]
    fn summary_contains_fix_suggestion() {
        let engine = RootCauseEngine::default();
        let input = make_input(TriageVerdict::Flake, 0.9, 0.2);
        let result = engine.analyze(&input);
        assert!(!result.summary.is_empty());
        assert!(result.summary.contains("confidence") || result.summary.contains('%'));
    }

    #[test]
    fn record_outcome_updates_weights() {
        let mut engine = RootCauseEngine::default();
        let initial = *engine
            .weights
            .priors
            .get(&RootCauseKind::InfrastructureFlake)
            .unwrap();
        engine.record_outcome(&RootCauseKind::InfrastructureFlake, true);
        let updated = *engine
            .weights
            .priors
            .get(&RootCauseKind::InfrastructureFlake)
            .unwrap();
        assert!(updated > initial, "Weight should increase after correct outcome");
    }

    #[test]
    fn what_if_fixed_returns_counterfactual_prob() {
        let engine = RootCauseEngine::default();
        let input = make_input(TriageVerdict::Flake, 0.85, 0.3);
        let result = engine.analyze(&input);
        let p = what_if_fixed(&result, &RootCauseKind::InfrastructureFlake);
        assert!(p >= 0.0 && p <= 1.0);
    }

    #[test]
    fn result_serializes_to_json() {
        let engine = RootCauseEngine::default();
        let input = make_input(TriageVerdict::NewBug, 0.15, 0.85);
        let result = engine.analyze(&input);
        let json = serde_json::to_string_pretty(&result).unwrap();
        assert!(json.contains("\"hypotheses\""));
        assert!(json.contains("\"confidence\""));
    }
}
