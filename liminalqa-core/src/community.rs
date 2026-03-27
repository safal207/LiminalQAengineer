//! Cross-project community pattern store — Q4 Month 10
//!
//! Enables LiminalQA instances to share anonymized failure patterns and
//! find similar patterns from other projects ("community resonance").
//!
//! # Architecture
//!
//! ```text
//!  Local project                Community DB (shared)
//!  ─────────────                ──────────────────────
//!  patterns ──export──► AnonymizedPattern ──import──► PatternStore
//!                                                          │
//!  new failure ──query──────────────────────────────► similar patterns
//!                                                          │
//!                                              suggested actions + context
//! ```
//!
//! # Similarity model
//!
//! Patterns are represented as a simple feature vector:
//! ```text
//! [failure_rate, flake_probability, mean_duration_ms (normalized),
//!  trend_slope (normalized), env_class (one-hot × 5)]
//! ```
//!
//! Cosine similarity is used for fast nearest-neighbour lookup.
//! No external ML library required — pure Rust arithmetic.

use crate::export::{AnonymizedPattern, EnvClass};
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Feature vector
// ---------------------------------------------------------------------------

const FEATURE_DIM: usize = 9;

type FeatureVec = [f64; FEATURE_DIM];

/// Encode an [`AnonymizedPattern`] as a normalizable feature vector.
///
/// Layout (indices):
/// 0 — failure_rate
/// 1 — flake_probability
/// 2 — mean_duration_ms / 10_000 (normalised to [0, ~1])
/// 3 — stddev_duration_ms / 10_000
/// 4 — trend_slope / 100
/// 5..8 — env_class one-hot: [prod, staging, dev, ci]
fn to_feature_vec(p: &AnonymizedPattern) -> FeatureVec {
    let s = &p.stats;
    let (ep, es, ed, ec) = env_onehot(&p.env_class);
    [
        s.failure_rate.clamp(0.0, 1.0),
        s.flake_probability.clamp(0.0, 1.0),
        (s.mean_duration_ms / 10_000.0).clamp(0.0, 1.0),
        (s.stddev_duration_ms / 10_000.0).clamp(0.0, 1.0),
        (s.trend_slope_ms_per_run / 100.0).clamp(-1.0, 1.0),
        ep,
        es,
        ed,
        ec,
    ]
}

fn env_onehot(env: &EnvClass) -> (f64, f64, f64, f64) {
    match env {
        EnvClass::Production => (1.0, 0.0, 0.0, 0.0),
        EnvClass::Staging => (0.0, 1.0, 0.0, 0.0),
        EnvClass::Development => (0.0, 0.0, 1.0, 0.0),
        EnvClass::Ci => (0.0, 0.0, 0.0, 1.0),
        EnvClass::Unknown => (0.0, 0.0, 0.0, 0.0),
    }
}

fn cosine_similarity(a: &FeatureVec, b: &FeatureVec) -> f64 {
    let dot: f64 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let mag_a: f64 = a.iter().map(|x| x * x).sum::<f64>().sqrt();
    let mag_b: f64 = b.iter().map(|x| x * x).sum::<f64>().sqrt();
    if mag_a < 1e-10 || mag_b < 1e-10 {
        return 0.0;
    }
    (dot / (mag_a * mag_b)).clamp(-1.0, 1.0)
}

// ---------------------------------------------------------------------------
// Stored entry
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StoredPattern {
    /// The anonymized pattern itself.
    pub pattern: AnonymizedPattern,
    /// How many times this pattern was seen (vote / upvote count).
    pub occurrence_count: u32,
    /// Comma-joined community-added tags (e.g. "flaky-db,timeout,known-infra").
    pub community_tags: Vec<String>,
    /// Effectiveness of the suggested action: 0.0–1.0 (derived from feedback).
    pub action_effectiveness: f64,
}

impl StoredPattern {
    fn new(pattern: AnonymizedPattern) -> Self {
        Self {
            pattern,
            occurrence_count: 1,
            community_tags: Vec::new(),
            action_effectiveness: 0.5,
        }
    }

    fn feature_vec(&self) -> FeatureVec {
        to_feature_vec(&self.pattern)
    }
}

// ---------------------------------------------------------------------------
// Pattern store
// ---------------------------------------------------------------------------

/// In-memory community pattern store with cosine-similarity nearest-neighbour
/// search.
///
/// In production this would be backed by PostgreSQL with `pgvector`.
/// This implementation uses a linear scan — fast enough for up to ~50 000
/// patterns; beyond that, use an HNSW index.
///
/// # Example
///
/// ```
/// use liminalqa_core::community::PatternStore;
/// use liminalqa_core::export::{AnonymizedPattern, EnvClass, PatternStats};
///
/// let mut store = PatternStore::new();
/// // Import community patterns…
/// // Query for matches to a local flake
/// let query = AnonymizedPattern {
///     test_token: "abc123".into(),
///     suite_token: "suite456".into(),
///     failure_kind: "flake".into(),
///     stats: PatternStats {
///         run_count: 30,
///         failure_rate: 0.25,
///         mean_duration_ms: 450.0,
///         stddev_duration_ms: 80.0,
///         flake_probability: 0.75,
///         trend_slope_ms_per_run: 0.0,
///     },
///     env_class: EnvClass::Ci,
///     tags: vec!["network".into()],
/// };
/// let matches = store.find_similar(&query, 5, 0.7);
/// println!("found {} community matches", matches.len());
/// ```
#[derive(Debug, Default)]
pub struct PatternStore {
    entries: Vec<StoredPattern>,
}

impl PatternStore {
    pub fn new() -> Self {
        Self::default()
    }

    /// Import a single anonymized pattern into the store.
    ///
    /// If a sufficiently similar pattern already exists (similarity ≥ 0.95),
    /// its `occurrence_count` is incremented instead of adding a duplicate.
    pub fn import(&mut self, pattern: AnonymizedPattern) {
        let fv = to_feature_vec(&pattern);
        // Check for near-duplicate
        for entry in &mut self.entries {
            let sim = cosine_similarity(&fv, &entry.feature_vec());
            if sim >= 0.95 {
                entry.occurrence_count += 1;
                return;
            }
        }
        self.entries.push(StoredPattern::new(pattern));
    }

    /// Import all patterns from an export bundle.
    pub fn import_bundle(&mut self, patterns: impl IntoIterator<Item = AnonymizedPattern>) {
        for p in patterns {
            self.import(p);
        }
    }

    /// Find the `top_k` most similar community patterns to `query`.
    ///
    /// Only returns patterns with similarity ≥ `min_similarity`.
    /// Results are ordered by similarity descending, then by occurrence_count
    /// descending (more common patterns rank higher among equals).
    pub fn find_similar(
        &self,
        query: &AnonymizedPattern,
        top_k: usize,
        min_similarity: f64,
    ) -> Vec<SimilarityMatch> {
        let qv = to_feature_vec(query);
        let mut scored: Vec<SimilarityMatch> = self
            .entries
            .iter()
            .filter_map(|entry| {
                let sim = cosine_similarity(&qv, &entry.feature_vec());
                if sim >= min_similarity {
                    Some(SimilarityMatch {
                        similarity: sim,
                        pattern: entry.pattern.clone(),
                        occurrence_count: entry.occurrence_count,
                        action_effectiveness: entry.action_effectiveness,
                        community_tags: entry.community_tags.clone(),
                    })
                } else {
                    None
                }
            })
            .collect();

        scored.sort_by(|a, b| {
            b.similarity
                .partial_cmp(&a.similarity)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.occurrence_count.cmp(&a.occurrence_count))
        });

        scored.truncate(top_k);
        scored
    }

    /// Record feedback on a pattern (did the suggested action help?).
    ///
    /// `effective`: true if the action resolved the problem.
    /// Updates effectiveness using a simple Bayesian moving average:
    /// `eff = (eff × n + outcome) / (n + 1)` where n is occurrence_count.
    pub fn record_feedback(&mut self, test_token: &str, effective: bool) {
        for entry in &mut self.entries {
            if entry.pattern.test_token == test_token {
                let n = entry.occurrence_count as f64;
                let outcome = if effective { 1.0 } else { 0.0 };
                entry.action_effectiveness =
                    (entry.action_effectiveness * n + outcome) / (n + 1.0);
                break;
            }
        }
    }

    /// Number of unique patterns in the store.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Return the top patterns by occurrence count (most widespread issues).
    pub fn top_patterns(&self, n: usize) -> Vec<&StoredPattern> {
        let mut sorted: Vec<&StoredPattern> = self.entries.iter().collect();
        sorted.sort_by(|a, b| b.occurrence_count.cmp(&a.occurrence_count));
        sorted.truncate(n);
        sorted
    }
}

// ---------------------------------------------------------------------------
// Similarity match result
// ---------------------------------------------------------------------------

/// A community pattern that matched a local pattern.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimilarityMatch {
    /// Cosine similarity (0.0–1.0) — higher is more similar.
    pub similarity: f64,
    /// The matching community pattern.
    pub pattern: AnonymizedPattern,
    /// How many projects reported this pattern.
    pub occurrence_count: u32,
    /// Fraction of reporters for whom the suggested action was effective.
    pub action_effectiveness: f64,
    /// Community-contributed tags.
    pub community_tags: Vec<String>,
}

impl SimilarityMatch {
    /// Human-readable confidence label.
    pub fn confidence_label(&self) -> &'static str {
        match self.similarity as u8 {
            _ if self.similarity >= 0.95 => "very_high",
            _ if self.similarity >= 0.85 => "high",
            _ if self.similarity >= 0.70 => "medium",
            _ => "low",
        }
    }
}

// ---------------------------------------------------------------------------
// Suggestion engine
// ---------------------------------------------------------------------------

/// Generates human-readable suggestions based on community matches.
pub struct CommunitySuggestion {
    pub action: String,
    pub rationale: String,
    pub confidence: &'static str,
    pub seen_by_n_projects: u32,
}

/// Distill top matches into actionable suggestions.
pub fn generate_suggestions(matches: &[SimilarityMatch]) -> Vec<CommunitySuggestion> {
    if matches.is_empty() {
        return vec![CommunitySuggestion {
            action: "observe".into(),
            rationale: "No community matches found — collect more data before acting.".into(),
            confidence: "low",
            seen_by_n_projects: 0,
        }];
    }

    // Tally action votes weighted by effectiveness × occurrence_count
    let mut action_scores: std::collections::HashMap<String, (f64, u32)> =
        std::collections::HashMap::new();

    for m in matches {
        let action = m.pattern.failure_kind.clone();
        let weight = m.similarity * m.action_effectiveness * m.occurrence_count as f64;
        let entry = action_scores.entry(action).or_insert((0.0, 0));
        entry.0 += weight;
        entry.1 += m.occurrence_count;
    }

    let best_match = &matches[0];
    let mut suggestions: Vec<CommunitySuggestion> = action_scores
        .into_iter()
        .map(|(action, (score, count))| CommunitySuggestion {
            action: action_to_suggestion(&action),
            rationale: format!(
                "Seen in {count} community reports with {:.0}% similarity to your pattern.",
                best_match.similarity * 100.0
            ),
            confidence: score_to_confidence(score),
            seen_by_n_projects: count,
        })
        .collect();

    suggestions.sort_by(|a, b| b.seen_by_n_projects.cmp(&a.seen_by_n_projects));
    suggestions
}

fn action_to_suggestion(kind: &str) -> String {
    match kind {
        "flake" => "Add retry logic with exponential backoff".into(),
        "new_bug" => "Investigate recent commits — likely a real regression".into(),
        "known_issue" => "Check issue tracker for existing ticket".into(),
        _ => format!("Review test '{kind}' failure pattern"),
    }
}

fn score_to_confidence(score: f64) -> &'static str {
    if score >= 10.0 {
        "high"
    } else if score >= 3.0 {
        "medium"
    } else {
        "low"
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::export::{AnonymizedPattern, EnvClass, PatternStats};

    fn make_pattern(
        test_token: &str,
        failure_rate: f64,
        flake_prob: f64,
        env: EnvClass,
        kind: &str,
    ) -> AnonymizedPattern {
        AnonymizedPattern {
            test_token: test_token.into(),
            suite_token: "suite_x".into(),
            failure_kind: kind.into(),
            stats: PatternStats {
                run_count: 50,
                failure_rate,
                mean_duration_ms: 500.0,
                stddev_duration_ms: 50.0,
                flake_probability: flake_prob,
                trend_slope_ms_per_run: 0.0,
            },
            env_class: env,
            tags: vec![],
        }
    }

    #[test]
    fn identical_patterns_have_similarity_one() {
        let p = make_pattern("t1", 0.3, 0.6, EnvClass::Ci, "flake");
        let fv = to_feature_vec(&p);
        let sim = cosine_similarity(&fv, &fv);
        assert!((sim - 1.0).abs() < 1e-9);
    }

    #[test]
    fn orthogonal_patterns_have_low_similarity() {
        let p1 = make_pattern("t1", 0.0, 0.0, EnvClass::Production, "flake");
        let p2 = make_pattern("t2", 0.0, 0.0, EnvClass::Ci, "flake");
        // Prod vs CI — env one-hot are orthogonal
        let s1 = to_feature_vec(&p1);
        let s2 = to_feature_vec(&p2);
        let sim = cosine_similarity(&s1, &s2);
        assert!(sim < 0.5, "Expected low similarity, got {sim:.3}");
    }

    #[test]
    fn import_deduplicates_near_identical() {
        let mut store = PatternStore::new();
        let p = make_pattern("t1", 0.3, 0.6, EnvClass::Ci, "flake");
        store.import(p.clone());
        store.import(p.clone());
        store.import(p);
        // Should merge into one entry with occurrence_count = 3
        assert_eq!(store.len(), 1);
        assert_eq!(store.entries[0].occurrence_count, 3);
    }

    #[test]
    fn find_similar_returns_top_k() {
        let mut store = PatternStore::new();
        for i in 0..20u32 {
            store.import(make_pattern(
                &format!("t{i}"),
                i as f64 * 0.04,
                i as f64 * 0.04,
                EnvClass::Ci,
                "flake",
            ));
        }
        let query = make_pattern("q", 0.5, 0.5, EnvClass::Ci, "flake");
        let results = store.find_similar(&query, 3, 0.0);
        assert!(results.len() <= 3);
        // Results should be sorted by similarity descending
        if results.len() >= 2 {
            assert!(results[0].similarity >= results[1].similarity);
        }
    }

    #[test]
    fn suggestions_generated_for_matches() {
        let mut store = PatternStore::new();
        store.import(make_pattern("t1", 0.4, 0.8, EnvClass::Ci, "flake"));
        let query = make_pattern("q", 0.4, 0.8, EnvClass::Ci, "flake");
        let matches = store.find_similar(&query, 5, 0.5);
        let suggestions = generate_suggestions(&matches);
        assert!(!suggestions.is_empty());
        assert!(suggestions[0].action.contains("retry"));
    }

    #[test]
    fn empty_store_returns_observe_suggestion() {
        let store = PatternStore::new();
        let query = make_pattern("q", 0.5, 0.5, EnvClass::Ci, "flake");
        let matches = store.find_similar(&query, 5, 0.5);
        let suggestions = generate_suggestions(&matches);
        assert_eq!(suggestions[0].action, "observe");
    }

    #[test]
    fn confidence_labels_are_correct() {
        let m = SimilarityMatch {
            similarity: 0.97,
            pattern: make_pattern("t", 0.1, 0.1, EnvClass::Ci, "flake"),
            occurrence_count: 1,
            action_effectiveness: 0.8,
            community_tags: vec![],
        };
        assert_eq!(m.confidence_label(), "very_high");
    }

    #[test]
    fn feedback_updates_effectiveness() {
        let mut store = PatternStore::new();
        let p = make_pattern("tok1", 0.3, 0.6, EnvClass::Ci, "flake");
        store.import(p);
        let initial = store.entries[0].action_effectiveness;
        store.record_feedback("tok1", true);
        // After one positive feedback, effectiveness should move toward 1.0
        assert!(store.entries[0].action_effectiveness >= initial);
    }
}
