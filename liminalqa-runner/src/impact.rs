//! Risk-ranked test selection from changed repository paths.
//!
//! The selector sits before [`crate::TestRunner`]:
//!
//! ```text
//! changed paths -> impact rules -> risk ranking -> bounded execution plan
//! ```
//!
//! It is deliberately deterministic and explainable. Every selected test carries
//! the path/rule matches and score components that caused it to enter the plan.

use serde::{Deserialize, Serialize};

/// Business criticality of the behavior covered by a test.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Criticality {
    Low,
    Medium,
    High,
    Critical,
}

impl Criticality {
    fn weight(self) -> f64 {
        match self {
            Self::Low => 0.25,
            Self::Medium => 0.50,
            Self::High => 0.75,
            Self::Critical => 1.0,
        }
    }
}

/// Explainable rule connecting a changed path to a test.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum ImpactRule {
    /// Strongest signal: the changed path starts with the supplied repository prefix.
    PathPrefix(String),
    /// Medium signal: the changed path contains the supplied normalized fragment.
    PathContains(String),
    /// Broad signal: the changed path has the supplied extension (`rs` or `.rs`).
    Extension(String),
}

impl ImpactRule {
    fn match_strength(&self, changed_path: &str) -> Option<f64> {
        let path = normalize_path(changed_path);
        match self {
            Self::PathPrefix(prefix) => path
                .starts_with(&normalize_path(prefix))
                .then_some(1.0),
            Self::PathContains(fragment) => path
                .contains(&normalize_path(fragment))
                .then_some(0.8),
            Self::Extension(extension) => {
                let extension = extension.trim().trim_start_matches('.').to_ascii_lowercase();
                (!extension.is_empty() && path.ends_with(&format!(".{extension}"))).then_some(0.6)
            }
        }
    }

    fn describe(&self) -> String {
        match self {
            Self::PathPrefix(value) => format!("path_prefix:{value}"),
            Self::PathContains(value) => format!("path_contains:{value}"),
            Self::Extension(value) => format!("extension:{value}"),
        }
    }
}

/// Catalog entry used by [`ImpactSelector`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TestDescriptor {
    pub name: String,
    pub suite: String,
    pub rules: Vec<ImpactRule>,
    pub criticality: Criticality,
    /// Fraction in the inclusive range `0.0..=1.0`.
    pub recent_failure_rate: f64,
    /// Fraction in the inclusive range `0.0..=1.0`.
    pub flake_probability: f64,
    pub average_duration_ms: u64,
    /// Eligible as a bounded safety-net when no impact rule matches.
    pub smoke: bool,
}

/// One concrete reason a test is connected to the current change set.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PathMatch {
    pub changed_path: String,
    pub rule: String,
    pub strength: f64,
}

/// A test selected for execution, with its evidence-backed ranking.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SelectedTest {
    pub name: String,
    pub suite: String,
    /// Normalized score in the inclusive range `0.0..=100.0`.
    pub risk_score: f64,
    pub criticality: Criticality,
    pub average_duration_ms: u64,
    pub path_matches: Vec<PathMatch>,
    pub reasons: Vec<String>,
}

/// Bounded, deterministic plan produced before test execution.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SelectionPlan {
    pub changed_paths: Vec<String>,
    pub selected: Vec<SelectedTest>,
    pub omitted_candidates: usize,
    pub fallback_used: bool,
    pub estimated_duration_ms: u64,
}

/// Controls how aggressively the selector narrows the suite.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ImpactSelectorConfig {
    pub max_tests: usize,
    /// Minimum normalized score (`0.0..=1.0`) for a directly matched test.
    pub minimum_score: f64,
    pub smoke_fallback_count: usize,
}

impl Default for ImpactSelectorConfig {
    fn default() -> Self {
        Self {
            max_tests: 20,
            minimum_score: 0.35,
            smoke_fallback_count: 3,
        }
    }
}

/// Deterministic risk-ranked test selector.
#[derive(Debug, Clone)]
pub struct ImpactSelector {
    config: ImpactSelectorConfig,
}

impl Default for ImpactSelector {
    fn default() -> Self {
        Self::new(ImpactSelectorConfig::default())
    }
}

impl ImpactSelector {
    pub fn new(config: ImpactSelectorConfig) -> Self {
        Self { config }
    }

    /// Build a minimal execution plan from changed repository paths and a test catalog.
    pub fn select(&self, changed_paths: &[String], catalog: &[TestDescriptor]) -> SelectionPlan {
        let normalized_paths: Vec<String> = changed_paths
            .iter()
            .map(|path| normalize_path(path))
            .collect();

        let mut candidates: Vec<SelectedTest> = catalog
            .iter()
            .filter_map(|test| self.score_direct_match(test, &normalized_paths))
            .filter(|test| test.risk_score >= clamp01(self.config.minimum_score) * 100.0)
            .collect();

        let fallback_used = candidates.is_empty();
        if fallback_used {
            candidates = catalog
                .iter()
                .filter(|test| test.smoke)
                .map(score_smoke_fallback)
                .collect();
        }

        sort_selected_tests(&mut candidates);

        let limit = if fallback_used {
            self.config
                .smoke_fallback_count
                .min(self.config.max_tests)
        } else {
            self.config.max_tests
        };
        let omitted_candidates = candidates.len().saturating_sub(limit);
        candidates.truncate(limit);
        let estimated_duration_ms = candidates
            .iter()
            .map(|test| test.average_duration_ms)
            .sum();

        SelectionPlan {
            changed_paths: normalized_paths,
            selected: candidates,
            omitted_candidates,
            fallback_used,
            estimated_duration_ms,
        }
    }

    fn score_direct_match(
        &self,
        test: &TestDescriptor,
        changed_paths: &[String],
    ) -> Option<SelectedTest> {
        let mut path_matches = Vec::new();

        for path in changed_paths {
            for rule in &test.rules {
                if let Some(strength) = rule.match_strength(path) {
                    path_matches.push(PathMatch {
                        changed_path: path.clone(),
                        rule: rule.describe(),
                        strength,
                    });
                }
            }
        }

        if path_matches.is_empty() {
            return None;
        }

        path_matches.sort_by(|left, right| {
            right
                .strength
                .total_cmp(&left.strength)
                .then_with(|| left.changed_path.cmp(&right.changed_path))
                .then_with(|| left.rule.cmp(&right.rule))
        });
        path_matches.dedup_by(|left, right| {
            left.changed_path == right.changed_path && left.rule == right.rule
        });

        let strongest_match = path_matches
            .iter()
            .map(|item| item.strength)
            .fold(0.0_f64, f64::max);
        let recent_failure_rate = clamp01(test.recent_failure_rate);
        let reliability = 1.0 - clamp01(test.flake_probability);

        // Match dominates the decision. Criticality and history refine ranking,
        // while reliability prevents a highly flaky detector from outranking a
        // stable detector with otherwise similar evidence.
        let normalized_score = strongest_match * 0.60
            + test.criticality.weight() * 0.20
            + recent_failure_rate * 0.15
            + reliability * 0.05;

        let reasons = vec![
            format!("strongest path match: {:.0}%", strongest_match * 100.0),
            format!("criticality: {:?}", test.criticality),
            format!("recent failure rate: {:.0}%", recent_failure_rate * 100.0),
            format!("detector reliability: {:.0}%", reliability * 100.0),
        ];

        Some(SelectedTest {
            name: test.name.clone(),
            suite: test.suite.clone(),
            risk_score: round_score(normalized_score * 100.0),
            criticality: test.criticality,
            average_duration_ms: test.average_duration_ms,
            path_matches,
            reasons,
        })
    }
}

fn score_smoke_fallback(test: &TestDescriptor) -> SelectedTest {
    let recent_failure_rate = clamp01(test.recent_failure_rate);
    let reliability = 1.0 - clamp01(test.flake_probability);
    let normalized_score = test.criticality.weight() * 0.55
        + recent_failure_rate * 0.25
        + reliability * 0.20;

    SelectedTest {
        name: test.name.clone(),
        suite: test.suite.clone(),
        risk_score: round_score(normalized_score * 100.0),
        criticality: test.criticality,
        average_duration_ms: test.average_duration_ms,
        path_matches: Vec::new(),
        reasons: vec![
            "smoke fallback: no direct impact rule matched".to_string(),
            format!("criticality: {:?}", test.criticality),
            format!("recent failure rate: {:.0}%", recent_failure_rate * 100.0),
            format!("detector reliability: {:.0}%", reliability * 100.0),
        ],
    }
}

fn sort_selected_tests(tests: &mut [SelectedTest]) {
    tests.sort_by(|left, right| {
        right
            .risk_score
            .total_cmp(&left.risk_score)
            .then_with(|| left.average_duration_ms.cmp(&right.average_duration_ms))
            .then_with(|| left.suite.cmp(&right.suite))
            .then_with(|| left.name.cmp(&right.name))
    });
}

fn normalize_path(path: &str) -> String {
    path.trim()
        .trim_start_matches("./")
        .replace('\\', "/")
        .to_ascii_lowercase()
}

fn clamp01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

fn round_score(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn descriptor(
        name: &str,
        rules: Vec<ImpactRule>,
        criticality: Criticality,
        smoke: bool,
    ) -> TestDescriptor {
        TestDescriptor {
            name: name.to_string(),
            suite: "demo".to_string(),
            rules,
            criticality,
            recent_failure_rate: 0.1,
            flake_probability: 0.05,
            average_duration_ms: 1_000,
            smoke,
        }
    }

    #[test]
    fn selects_only_tests_connected_to_changed_paths() {
        let catalog = vec![
            descriptor(
                "auth_refresh",
                vec![ImpactRule::PathPrefix("services/auth/".to_string())],
                Criticality::Critical,
                false,
            ),
            descriptor(
                "trading_order",
                vec![ImpactRule::PathPrefix("services/trading/".to_string())],
                Criticality::Critical,
                false,
            ),
        ];

        let plan = ImpactSelector::default().select(
            &["services/auth/src/token.rs".to_string()],
            &catalog,
        );

        assert_eq!(plan.selected.len(), 1);
        assert_eq!(plan.selected[0].name, "auth_refresh");
        assert!(!plan.fallback_used);
    }

    #[test]
    fn uses_bounded_smoke_fallback_when_nothing_matches() {
        let catalog = vec![
            descriptor("home_smoke", Vec::new(), Criticality::High, true),
            descriptor("login_smoke", Vec::new(), Criticality::Critical, true),
            descriptor("unrelated", Vec::new(), Criticality::Critical, false),
        ];
        let selector = ImpactSelector::new(ImpactSelectorConfig {
            max_tests: 10,
            minimum_score: 0.35,
            smoke_fallback_count: 1,
        });

        let plan = selector.select(&["docs/readme.md".to_string()], &catalog);

        assert!(plan.fallback_used);
        assert_eq!(plan.selected.len(), 1);
        assert_eq!(plan.selected[0].name, "login_smoke");
        assert_eq!(plan.omitted_candidates, 1);
    }

    #[test]
    fn normalizes_windows_paths_and_extensions() {
        let catalog = vec![descriptor(
            "rust_core",
            vec![ImpactRule::Extension(".rs".to_string())],
            Criticality::Medium,
            false,
        )];

        let plan = ImpactSelector::default().select(
            &[r".\liminalqa-core\src\types.rs".to_string()],
            &catalog,
        );

        assert_eq!(plan.changed_paths, vec!["liminalqa-core/src/types.rs"]);
        assert_eq!(plan.selected[0].name, "rust_core");
    }

    #[test]
    fn ranking_is_deterministic_and_prefers_higher_risk() {
        let mut critical = descriptor(
            "critical_auth",
            vec![ImpactRule::PathContains("auth".to_string())],
            Criticality::Critical,
            false,
        );
        critical.average_duration_ms = 2_000;

        let medium = descriptor(
            "medium_auth",
            vec![ImpactRule::PathContains("auth".to_string())],
            Criticality::Medium,
            false,
        );

        let plan = ImpactSelector::default().select(
            &["services/auth/src/token.rs".to_string()],
            &[medium, critical],
        );

        assert_eq!(plan.selected[0].name, "critical_auth");
        assert!(plan.selected[0].risk_score > plan.selected[1].risk_score);
    }
}
