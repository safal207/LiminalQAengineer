//! Anonymized pattern export — Q4 Month 10
//!
//! Strips PII (test names, URLs, IPs, file paths) and hashes identifiers so
//! that patterns can be contributed to a shared community knowledge base
//! without leaking internal service names or infrastructure details.
//!
//! # Design
//!
//! * **One-way hashing** — identifiers are SHA-256 hashed with a per-export
//!   salt so the same test name always maps to the same anonymous token
//!   *within* a single export, enabling correlation, but not across exports.
//! * **Structural preservation** — all numeric signals, timings, and
//!   statistical summaries are kept as-is; only string identifiers are
//!   anonymized.
//! * **Opt-in** — callers must explicitly construct an [`Anonymizer`] and
//!   call [`Anonymizer::anonymize_pattern`]; nothing happens automatically.
//!
//! # Export format
//!
//! ```json
//! {
//!   "schema_version": "1.0",
//!   "export_id": "550e8400-...",
//!   "exported_at": "2025-10-01T00:00:00Z",
//!   "patterns": [...]
//! }
//! ```

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Exported pattern types
// ---------------------------------------------------------------------------

/// A single anonymized failure pattern ready for community contribution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnonymizedPattern {
    /// Anonymous stable token for the test (SHA-256 of salt + original name).
    pub test_token: String,
    /// Anonymous token for the suite / project.
    pub suite_token: String,
    /// Failure category as classified by triage (flake / new_bug / known_issue).
    pub failure_kind: String,
    /// Statistical summary — no raw values, only aggregates.
    pub stats: PatternStats,
    /// Environment class (prod/staging/dev) — not the actual env name.
    pub env_class: EnvClass,
    /// Tags describing the pattern (timeout, network, assertion, crash…).
    pub tags: Vec<String>,
}

/// Numeric summary of a pattern — safe to share as-is.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatternStats {
    /// Total runs included in this pattern.
    pub run_count: u32,
    /// Fraction of runs that failed (0.0–1.0).
    pub failure_rate: f64,
    /// Mean duration in milliseconds.
    pub mean_duration_ms: f64,
    /// Standard deviation of duration.
    pub stddev_duration_ms: f64,
    /// Flake probability from predictive model (0.0–1.0).
    pub flake_probability: f64,
    /// Duration trend slope (ms/run) — positive = getting slower.
    pub trend_slope_ms_per_run: f64,
}

/// Coarse environment class — safe to export without revealing infra topology.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EnvClass {
    Production,
    Staging,
    Development,
    Ci,
    Unknown,
}

// ---------------------------------------------------------------------------
// Export bundle
// ---------------------------------------------------------------------------

/// Complete export bundle — the thing you POST to the community patterns API.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatternExportBundle {
    pub schema_version: &'static str,
    /// Opaque export identifier (random UUID, not tied to any internal ID).
    pub export_id: String,
    pub exported_at: String,
    pub patterns: Vec<AnonymizedPattern>,
    /// How many patterns were dropped because of insufficient data.
    pub dropped_low_data: u32,
    /// Total patterns before filtering.
    pub total_candidates: u32,
}

// ---------------------------------------------------------------------------
// Anonymizer
// ---------------------------------------------------------------------------

/// Converts internal pattern data into anonymized, shareable form.
///
/// # Example
///
/// ```no_run
/// use liminalqa_core::export::Anonymizer;
///
/// let salt = b"my-secret-per-export-salt";
/// let mut anon = Anonymizer::new(salt);
/// let token = anon.hash_identifier("payments::charge_card");
/// assert_eq!(token.len(), 16); // hex-truncated
/// ```
pub struct Anonymizer {
    salt: Vec<u8>,
    /// Cache so the same name always maps to the same token within an export.
    cache: HashMap<String, String>,
}

impl Anonymizer {
    /// Create a new anonymizer with the given per-export salt.
    ///
    /// The salt prevents cross-export correlation while keeping intra-export
    /// token stability.
    pub fn new(salt: &[u8]) -> Self {
        Self {
            salt: salt.to_vec(),
            cache: HashMap::new(),
        }
    }

    /// Hash an identifier (test name, suite name, URL …) to a stable token.
    ///
    /// Returns the first 16 hex chars of SHA-256(salt ‖ identifier).
    /// That's 64 bits — plenty for correlation, negligible collision risk.
    pub fn hash_identifier(&mut self, id: &str) -> String {
        if let Some(cached) = self.cache.get(id) {
            return cached.clone();
        }
        let mut hasher = Sha256::new();
        hasher.update(&self.salt);
        hasher.update(id.as_bytes());
        let digest = hasher.finalize();
        // Take first 8 bytes → 16 hex chars
        let token: String = digest[..8].iter().map(|b| format!("{b:02x}")).collect();
        self.cache.insert(id.to_owned(), token.clone());
        token
    }

    /// Strip well-known PII patterns from a free-text string.
    ///
    /// Replaces:
    /// - IPv4 addresses with `<ip>`
    /// - URLs / hostnames with `<url>`
    /// - File paths with `<path>`
    /// - ULIDs / UUIDs with `<id>`
    pub fn sanitize_text(text: &str) -> String {
        // Simple regex-free replacements using basic string scanning.
        // A production impl would use a proper regex crate.
        let mut out = text.to_owned();

        // UUID pattern (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
        out = replace_pattern(&out, &UUID_LIKE, "<id>");

        // IPv4 addresses
        out = replace_pattern(&out, &IPV4_LIKE, "<ip>");

        // URLs
        out = replace_pattern(&out, &URL_LIKE, "<url>");

        // Unix-style absolute paths
        out = replace_pattern(&out, &PATH_LIKE, "<path>");

        out
    }

    /// Build an anonymized pattern from raw inputs.
    ///
    /// Always returns a pattern; the caller is responsible for the `min_runs`
    /// check (see [`ExportBuilder`]) to stay within clippy's argument limit.
    pub fn anonymize_pattern(
        &mut self,
        test_name: &str,
        suite_name: &str,
        failure_kind: &str,
        stats: PatternStats,
        env_class: EnvClass,
        tags: Vec<String>,
    ) -> AnonymizedPattern {
        let test_token = self.hash_identifier(test_name);
        let suite_token = self.hash_identifier(suite_name);
        AnonymizedPattern {
            test_token,
            suite_token,
            failure_kind: failure_kind.to_owned(),
            stats,
            env_class,
            tags,
        }
    }
}

// ---------------------------------------------------------------------------
// Naive pattern replacement helpers (no regex dependency)
// ---------------------------------------------------------------------------

struct PatternSpec {
    /// Characters that can appear in a match (fast pre-filter).
    prefix: &'static str,
    /// Minimum match length.
    min_len: usize,
    /// Validation predicate.
    validate: fn(&str) -> bool,
}

static UUID_LIKE: PatternSpec = PatternSpec {
    prefix: "-",
    min_len: 36,
    validate: |s| {
        // xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        let b = s.as_bytes();
        b.len() == 36
            && b[8] == b'-'
            && b[13] == b'-'
            && b[18] == b'-'
            && b[23] == b'-'
            && b.iter().enumerate().all(|(i, c)| {
                if [8, 13, 18, 23].contains(&i) {
                    *c == b'-'
                } else {
                    c.is_ascii_hexdigit()
                }
            })
    },
};

static IPV4_LIKE: PatternSpec = PatternSpec {
    prefix: ".",
    min_len: 7,
    validate: |s| {
        let parts: Vec<&str> = s.split('.').collect();
        parts.len() == 4
            && parts.iter().all(|p| {
                let n: Result<u32, _> = p.parse();
                n.map(|v| v <= 255).unwrap_or(false)
            })
    },
};

static URL_LIKE: PatternSpec = PatternSpec {
    prefix: "://",
    min_len: 8,
    validate: |s| s.starts_with("http://") || s.starts_with("https://"),
};

static PATH_LIKE: PatternSpec = PatternSpec {
    prefix: "/",
    min_len: 3,
    validate: |s| s.starts_with('/') && s.contains('/'),
};

fn replace_pattern(text: &str, spec: &PatternSpec, replacement: &str) -> String {
    // Walk through looking for token boundaries.  Very naive — good enough
    // for log lines; a production impl would use the `regex` crate.
    let chars: Vec<char> = text.chars().collect();
    let mut result = String::with_capacity(text.len());
    let mut i = 0;

    while i < chars.len() {
        // Find a potential start based on prefix character
        let ch = chars[i];
        let prefix_char = spec.prefix.chars().next().unwrap_or('\0');

        if ch == prefix_char || ch.is_alphanumeric() {
            // Try to collect a token
            let start = i;
            let mut j = i;
            while j < chars.len()
                && (chars[j].is_alphanumeric()
                    || chars[j] == '-'
                    || chars[j] == '.'
                    || chars[j] == '/'
                    || chars[j] == ':'
                    || chars[j] == '_')
            {
                j += 1;
            }
            let token: String = chars[start..j].iter().collect();
            if token.len() >= spec.min_len && (spec.validate)(&token) {
                result.push_str(replacement);
                i = j;
                continue;
            }
        }
        result.push(chars[i]);
        i += 1;
    }
    result
}

// ---------------------------------------------------------------------------
// Export builder
// ---------------------------------------------------------------------------

/// Builds a complete [`PatternExportBundle`] from a collection of raw patterns.
pub struct ExportBuilder {
    anonymizer: Anonymizer,
    min_runs: u32,
    patterns: Vec<(String, String, String, PatternStats, EnvClass, Vec<String>)>,
}

impl ExportBuilder {
    /// Create a new builder.
    ///
    /// `salt` — unique per export; use a random UUID or timestamp.
    /// `min_runs` — patterns with fewer runs are dropped (default 5).
    pub fn new(salt: &[u8], min_runs: u32) -> Self {
        Self {
            anonymizer: Anonymizer::new(salt),
            min_runs,
            patterns: Vec::new(),
        }
    }

    /// Add a pattern candidate.
    pub fn add(
        &mut self,
        test_name: impl Into<String>,
        suite_name: impl Into<String>,
        failure_kind: impl Into<String>,
        stats: PatternStats,
        env_class: EnvClass,
        tags: Vec<String>,
    ) {
        self.patterns.push((
            test_name.into(),
            suite_name.into(),
            failure_kind.into(),
            stats,
            env_class,
            tags,
        ));
    }

    /// Finalize and produce the [`PatternExportBundle`].
    pub fn build(mut self) -> PatternExportBundle {
        let total = self.patterns.len() as u32;
        let mut exported = Vec::new();
        let mut dropped = 0u32;

        for (test, suite, kind, stats, env, tags) in self.patterns {
            if stats.run_count < self.min_runs {
                dropped += 1;
                continue;
            }
            let p = self
                .anonymizer
                .anonymize_pattern(&test, &suite, &kind, stats, env, tags);
            exported.push(p);
        }

        // Stable sort: highest failure-rate patterns first (most interesting)
        exported.sort_by(|a, b| {
            b.stats
                .failure_rate
                .partial_cmp(&a.stats.failure_rate)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        PatternExportBundle {
            schema_version: "1.0",
            export_id: new_export_id(),
            exported_at: chrono::Utc::now().to_rfc3339(),
            patterns: exported,
            dropped_low_data: dropped,
            total_candidates: total,
        }
    }
}

fn new_export_id() -> String {
    // Deterministic pseudo-random ID based on current time (no uuid crate dep)
    use std::time::{SystemTime, UNIX_EPOCH};
    let ns = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("exp-{ns:x}")
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_stats(run_count: u32, failure_rate: f64) -> PatternStats {
        PatternStats {
            run_count,
            failure_rate,
            mean_duration_ms: 120.0,
            stddev_duration_ms: 15.0,
            flake_probability: failure_rate * 0.8,
            trend_slope_ms_per_run: 0.5,
        }
    }

    #[test]
    fn hash_is_stable_within_export() {
        let mut anon = Anonymizer::new(b"test-salt");
        let t1 = anon.hash_identifier("payments::charge");
        let t2 = anon.hash_identifier("payments::charge");
        assert_eq!(t1, t2);
        assert_eq!(t1.len(), 16);
    }

    #[test]
    fn different_names_produce_different_tokens() {
        let mut anon = Anonymizer::new(b"test-salt");
        let t1 = anon.hash_identifier("test_a");
        let t2 = anon.hash_identifier("test_b");
        assert_ne!(t1, t2);
    }

    #[test]
    fn different_salts_produce_different_tokens() {
        let mut a1 = Anonymizer::new(b"salt-one");
        let mut a2 = Anonymizer::new(b"salt-two");
        let t1 = a1.hash_identifier("payments::charge");
        let t2 = a2.hash_identifier("payments::charge");
        assert_ne!(t1, t2);
    }

    #[test]
    fn min_runs_filter_drops_low_data() {
        let mut builder = ExportBuilder::new(b"salt", 10);
        builder.add(
            "test::low_data",
            "suite_a",
            "flake",
            make_stats(3, 0.4),
            EnvClass::Ci,
            vec!["timeout".into()],
        );
        builder.add(
            "test::enough_data",
            "suite_a",
            "flake",
            make_stats(20, 0.6),
            EnvClass::Ci,
            vec!["timeout".into()],
        );
        let bundle = builder.build();
        assert_eq!(bundle.patterns.len(), 1);
        assert_eq!(bundle.dropped_low_data, 1);
        assert_eq!(bundle.total_candidates, 2);
    }

    #[test]
    fn patterns_sorted_by_failure_rate_descending() {
        let mut builder = ExportBuilder::new(b"salt", 1);
        builder.add(
            "t1",
            "s",
            "flake",
            make_stats(10, 0.2),
            EnvClass::Ci,
            vec![],
        );
        builder.add(
            "t2",
            "s",
            "flake",
            make_stats(10, 0.8),
            EnvClass::Ci,
            vec![],
        );
        builder.add(
            "t3",
            "s",
            "flake",
            make_stats(10, 0.5),
            EnvClass::Ci,
            vec![],
        );
        let bundle = builder.build();
        let rates: Vec<f64> = bundle
            .patterns
            .iter()
            .map(|p| p.stats.failure_rate)
            .collect();
        assert!(rates[0] >= rates[1] && rates[1] >= rates[2]);
    }

    #[test]
    fn export_bundle_serializes_to_json() {
        let mut builder = ExportBuilder::new(b"salt", 1);
        builder.add(
            "auth::login",
            "auth_suite",
            "new_bug",
            make_stats(50, 0.15),
            EnvClass::Production,
            vec!["regression".into()],
        );
        let bundle = builder.build();
        let json = serde_json::to_string_pretty(&bundle).unwrap();
        assert!(json.contains("\"schema_version\""));
        assert!(json.contains("\"patterns\""));
        assert!(!json.contains("auth::login")); // original name must not appear
    }

    #[test]
    fn sanitize_text_strips_ip() {
        let text = "Connection to 192.168.1.100 failed";
        let sanitized = Anonymizer::sanitize_text(text);
        assert!(
            !sanitized.contains("192.168.1.100"),
            "IP not stripped: {sanitized}"
        );
    }
}
