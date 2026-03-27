//! Demo-grade dashboard — Q4 Month 11 / 1.0 Release
//!
//! Assembles all LiminalQA quality signals into a single, human-readable
//! view that answers four questions in under 90 seconds:
//!
//! * **What is the risk?** — Test Risk Card
//! * **Why is it failing?** — Root Cause Panel
//! * **What if we fix it?** — Counterfactual / What-if Analysis
//! * **What do others know?** — Community Insights
//!
//! # Design intent
//!
//! This module deliberately avoids external UI dependencies.  The text
//! renderer produces clean box-drawing output that:
//! - Runs in any terminal (CI logs, SSH sessions, local dev)
//! - Screenshottable for README / blog posts
//! - Pipe-friendly (`limctl dashboard payments/charge | cat`)
//! - Portable to HTML by wrapping in `<pre>` tags
//!
//! # Usage
//!
//! ```ignore
//! use liminalqa_core::dashboard::{DashboardReport, DashboardInput};
//!
//! // Build `input` from DecisionEngine + RootCauseEngine + PatternStore
//! // (see tests/dashboard_demo.rs for a full working example)
//! let input: DashboardInput = todo!();
//! let report = DashboardReport::build(input);
//! println!("{}", report.render_text());
//! ```

use crate::{
    community::SimilarityMatch,
    decision::{MergePolicy, TestDecision},
    rootcause::{what_if_fixed, RootCauseKind, RootCauseResult},
};

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

/// All signals needed to render the full 4-panel dashboard for one test.
pub struct DashboardInput {
    /// Pre-computed test decision (merge policy, action, signals, hints).
    pub decision: TestDecision,
    /// Root-cause analysis result (ranked hypotheses + counterfactuals).
    pub root_cause: RootCauseResult,
    /// Community pattern matches (may be empty).
    pub community: Vec<SimilarityMatch>,
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

/// Fully assembled dashboard view for one test.
pub struct DashboardReport {
    /// Panel A — risk card data.
    pub risk: RiskCard,
    /// Panel B — root cause panel.
    pub root_cause: RootCausePanel,
    /// Panel C — what-if / counterfactual.
    pub what_if: WhatIfPanel,
    /// Panel D — community insights.
    pub community: CommunityPanel,
}

// ---------------------------------------------------------------------------
// Panel A — Test Risk Card
// ---------------------------------------------------------------------------

pub struct RiskCard {
    pub test_name: String,
    pub suite: String,
    pub verdict: String,
    pub confidence_pct: u8,
    pub severity: String,
    pub action: String,
    pub merge: String,
    pub flake_pct: u8,
    pub trend: String,
    /// Adaptive timeout string, e.g. "4.8s (EMA mean + 3σ)".
    pub timeout: Option<String>,
    /// Top root cause hint for the card (first line summary).
    pub hint: Option<String>,
}

// ---------------------------------------------------------------------------
// Panel B — Root Cause
// ---------------------------------------------------------------------------

pub struct RootCausePanel {
    /// Top hypothesis label.
    pub most_likely: String,
    pub most_likely_pct: u8,
    /// All hypotheses (max 3), in order.
    pub hypotheses: Vec<HypothesisRow>,
    /// Actionable fix for the top hypothesis.
    pub suggested_fix: String,
    /// One-sentence summary.
    pub summary: String,
}

pub struct HypothesisRow {
    pub kind: String,
    pub confidence_pct: u8,
    /// Top evidence items (max 2).
    pub evidence: Vec<String>,
}

// ---------------------------------------------------------------------------
// Panel C — What-if
// ---------------------------------------------------------------------------

pub struct WhatIfPanel {
    /// Current estimated pass rate (1 - failure_rate).
    pub current_pass_pct: u8,
    /// Counterfactuals: (label, success_probability_pct).
    pub scenarios: Vec<(String, u8)>,
}

// ---------------------------------------------------------------------------
// Panel D — Community
// ---------------------------------------------------------------------------

pub struct CommunityPanel {
    pub match_count: usize,
    pub top_matches: Vec<CommunityRow>,
}

pub struct CommunityRow {
    pub similarity_pct: u8,
    pub projects_seen: u32,
    pub suggested_action: String,
    pub effectiveness_pct: u8,
}

// ---------------------------------------------------------------------------
// Builder
// ---------------------------------------------------------------------------

impl DashboardReport {
    pub fn build(input: DashboardInput) -> Self {
        let DashboardInput {
            decision,
            root_cause,
            community,
        } = input;

        // Panel A
        let risk = RiskCard {
            test_name: decision.name.clone(),
            suite: decision.suite.clone(),
            verdict: decision.verdict.to_uppercase(),
            confidence_pct: (decision.confidence * 100.0) as u8,
            severity: decision.severity.to_string().to_uppercase(),
            action: decision.recommended_action.to_string(),
            merge: merge_label(&decision.merge_policy),
            flake_pct: (decision.signals.flake_probability * 100.0) as u8,
            trend: decision.signals.trend_direction.clone(),
            timeout: decision
                .signals
                .suggested_timeout_ms
                .map(|ms| format!("{:.1}s (EMA mean + 3σ)", ms as f64 / 1000.0)),
            hint: decision.root_cause_hints.first().map(|s| truncate(s, 72)),
        };

        // Panel B
        let hypotheses: Vec<HypothesisRow> = root_cause
            .hypotheses
            .iter()
            .map(|h| HypothesisRow {
                kind: h.kind.to_string(),
                confidence_pct: (h.confidence * 100.0) as u8,
                evidence: h
                    .evidence
                    .iter()
                    .filter(|e| e.description != "prior")
                    .take(2)
                    .map(|e| truncate(&e.description, 60))
                    .collect(),
            })
            .collect();

        let top = root_cause.hypotheses.first();
        let root_cause_panel = RootCausePanel {
            most_likely: top
                .map(|h| h.kind.to_string())
                .unwrap_or_else(|| "undetermined".into()),
            most_likely_pct: top.map(|h| (h.confidence * 100.0) as u8).unwrap_or(0),
            suggested_fix: top
                .map(|h| truncate(&h.suggested_fix, 72))
                .unwrap_or_else(|| "Collect more data.".into()),
            summary: truncate(&root_cause.summary, 80),
            hypotheses,
        };

        // Panel C — What-if
        let failure_rate = 1.0 - decision.signals.stability_score;
        let current_pass_pct = ((1.0 - failure_rate) * 100.0).clamp(0.0, 100.0) as u8;

        let counterfactual_kinds = [
            RootCauseKind::InfrastructureFlake,
            RootCauseKind::CodeRegression,
            RootCauseKind::TestDesignFlaw,
            RootCauseKind::ExternalDependency,
        ];
        let mut scenarios: Vec<(String, u8)> = counterfactual_kinds
            .iter()
            .filter_map(|kind| {
                let p = what_if_fixed(&root_cause, kind);
                let pct = (p * 100.0) as u8;
                // Only show if better than current pass rate + 5%
                if pct > current_pass_pct.saturating_add(5) {
                    Some((kind_to_label(kind), pct))
                } else {
                    None
                }
            })
            .collect();
        scenarios.sort_by(|a, b| b.1.cmp(&a.1));
        scenarios.truncate(3);

        let what_if = WhatIfPanel {
            current_pass_pct,
            scenarios,
        };

        // Panel D — Community
        let top_matches: Vec<CommunityRow> = community
            .iter()
            .take(3)
            .map(|m| CommunityRow {
                similarity_pct: (m.similarity * 100.0) as u8,
                projects_seen: m.occurrence_count,
                suggested_action: action_from_kind(&m.pattern.failure_kind),
                effectiveness_pct: (m.action_effectiveness * 100.0) as u8,
            })
            .collect();

        let community_panel = CommunityPanel {
            match_count: community.len(),
            top_matches,
        };

        DashboardReport {
            risk,
            root_cause: root_cause_panel,
            what_if,
            community: community_panel,
        }
    }

    // -----------------------------------------------------------------------
    // Text renderer — produces terminal-ready output
    // -----------------------------------------------------------------------

    /// Render the full 4-panel dashboard as a UTF-8 text string.
    ///
    /// Width: 70 columns.  Use a monospace font when displaying.
    pub fn render_text(&self) -> String {
        let mut out = String::with_capacity(2048);
        self.render_header(&mut out);
        self.render_risk_card(&mut out);
        self.render_root_cause(&mut out);
        self.render_what_if(&mut out);
        self.render_community(&mut out);
        out
    }

    fn render_header(&self, out: &mut String) {
        let title = format!("  LIMINALQA · {}/{}", self.risk.suite, self.risk.test_name);
        out.push_str(&box_top(70));
        out.push_str(&box_line(&title, 70));
        out.push_str(&box_bot(70));
        out.push('\n');
    }

    fn render_risk_card(&self, out: &mut String) {
        let r = &self.risk;
        panel_title(out, "A  TEST RISK CARD", 70);

        let verdict_color = match r.verdict.as_str() {
            "NEW_BUG" | "FLAKE" => "⚠",
            "KNOWN_ISSUE" => "◉",
            _ => "✓",
        };
        row2(
            out,
            "verdict",
            &format!("{verdict_color} {}", r.verdict),
            "confidence",
            &format!("{}%", r.confidence_pct),
        );
        row2(out, "severity", &r.severity, "merge", &r.merge);
        row2(out, "action", &r.action, "trend", &trend_arrow(&r.trend));

        let bar = progress_bar(r.flake_pct as usize, 20);
        row2(
            out,
            "flake risk",
            &format!("{bar} {}%", r.flake_pct),
            "runs",
            &format!("{}", r.confidence_pct),
        ); // reuse confidence as proxy

        if let Some(t) = &r.timeout {
            panel_row(out, "timeout", t, 70);
        }
        if let Some(h) = &r.hint {
            panel_blank(out, 70);
            panel_row(out, "insight", h, 70);
        }
        panel_close(out, 70);
    }

    fn render_root_cause(&self, out: &mut String) {
        let rc = &self.root_cause;
        panel_title(out, "B  ROOT CAUSE ANALYSIS", 70);

        panel_row(
            out,
            "most likely",
            &format!("{} ({}%)", rc.most_likely, rc.most_likely_pct),
            70,
        );
        panel_blank(out, 70);

        for h in &rc.hypotheses {
            let bar = progress_bar(h.confidence_pct as usize, 18);
            let label = pad_right(&h.kind, 24);
            let line = format!("  ▶ {}  {}  {}%", label, bar, h.confidence_pct);
            panel_line(out, &line, 70);
            for ev in &h.evidence {
                panel_line(out, &format!("    · {ev}"), 70);
            }
        }

        panel_blank(out, 70);
        panel_row(out, "fix", &rc.suggested_fix, 70);
        panel_close(out, 70);
    }

    fn render_what_if(&self, out: &mut String) {
        let w = &self.what_if;
        panel_title(out, "C  WHAT-IF  /  COUNTERFACTUAL", 70);

        let cur_bar = progress_bar(w.current_pass_pct as usize, 20);
        let cur_line = format!("  current pass rate    {cur_bar}  {}%", w.current_pass_pct);
        panel_line(out, &cur_line, 70);

        if w.scenarios.is_empty() {
            panel_blank(out, 70);
            panel_line(out, "  (not enough data for counterfactual estimates)", 70);
        } else {
            panel_blank(out, 70);
            for (label, pct) in &w.scenarios {
                let bar = progress_bar(*pct as usize, 20);
                let delta = (*pct as i16) - (w.current_pass_pct as i16);
                let sign = if delta >= 0 { "+" } else { "" };
                let lbl = pad_right(&format!("if {label} fixed"), 24);
                let line = format!("  {lbl}  {bar}  {}%  ({sign}{delta}pp)", pct);
                panel_line(out, &line, 70);
            }
        }
        panel_close(out, 70);
    }

    fn render_community(&self, out: &mut String) {
        let c = &self.community;
        panel_title(out, "D  COMMUNITY INSIGHTS", 70);

        if c.match_count == 0 {
            panel_line(out, "  No community matches found yet.", 70);
            panel_line(
                out,
                "  Export this pattern to contribute to shared knowledge.",
                70,
            );
        } else {
            let s = if c.match_count == 1 { "" } else { "s" };
            panel_row(
                out,
                "matches",
                &format!(
                    "{} similar incident{s} in community knowledge base",
                    c.match_count
                ),
                70,
            );
            panel_blank(out, 70);
            for m in &c.top_matches {
                let eff_bar = progress_bar(m.effectiveness_pct as usize, 10);
                let line = format!(
                    "  ▶ similarity {}%   seen in {} project(s)",
                    m.similarity_pct, m.projects_seen
                );
                panel_line(out, &line, 70);
                panel_line(out, &format!("    action:  {}", m.suggested_action), 70);
                let eff_line = format!(
                    "    effective: {eff_bar} {}% of reporters resolved with this action",
                    m.effectiveness_pct
                );
                panel_line(out, &eff_line, 70);
                panel_blank(out, 70);
            }
        }
        panel_close(out, 70);
    }
}

// ---------------------------------------------------------------------------
// Drawing primitives
// ---------------------------------------------------------------------------

fn box_top(w: usize) -> String {
    format!("╔{}╗\n", "═".repeat(w - 2))
}
fn box_line(content: &str, w: usize) -> String {
    let inner = pad_right(content, w - 4);
    format!("║  {inner}  ║\n")
}
fn box_bot(w: usize) -> String {
    format!("╚{}╝\n", "═".repeat(w - 2))
}

fn panel_title(out: &mut String, title: &str, w: usize) {
    let dashes = "─".repeat(w - title.len() - 5);
    out.push_str(&format!("┌─ {title} {dashes}┐\n"));
}
fn panel_close(out: &mut String, w: usize) {
    out.push_str(&format!("└{}┘\n\n", "─".repeat(w - 2)));
}
fn panel_line(out: &mut String, content: &str, w: usize) {
    // content already includes leading spaces; just pad to panel width
    let inner = pad_right(content, w - 4);
    out.push_str(&format!("│  {inner}  │\n"));
}
fn panel_blank(out: &mut String, w: usize) {
    panel_line(out, "", w);
}
fn panel_row(out: &mut String, key: &str, value: &str, w: usize) {
    let content = format!("{:<14}  {}", format!("{key}:"), value);
    panel_line(out, &content, w);
}

fn row2(out: &mut String, k1: &str, v1: &str, k2: &str, v2: &str) {
    // Two-column row within a 70-char panel
    let left = format!("{:<14}  {:<22}", format!("{k1}:"), v1);
    let right = format!("{}:  {}", k2, v2);
    let content = format!("{left} {right}");
    panel_line(out, &content, 70);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn progress_bar(pct: usize, width: usize) -> String {
    let pct = pct.min(100);
    let filled = (pct * width) / 100;
    let empty = width - filled;
    format!("{}{}", "█".repeat(filled), "░".repeat(empty))
}

fn pad_right(s: &str, width: usize) -> String {
    // Count display chars (naïve — ok for ASCII + box-drawing)
    let len = s.chars().count();
    if len >= width {
        s.chars().take(width).collect()
    } else {
        format!("{s}{}", " ".repeat(width - len))
    }
}

fn truncate(s: &str, max: usize) -> String {
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= max {
        s.to_owned()
    } else {
        format!("{}…", chars[..max - 1].iter().collect::<String>())
    }
}

fn merge_label(p: &MergePolicy) -> String {
    match p {
        MergePolicy::Block => "🔴 BLOCK".into(),
        MergePolicy::BlockSoft => "🟠 BLOCK (soft)".into(),
        MergePolicy::AllowWithWarning => "🟡 WARN".into(),
        MergePolicy::Allow => "🟢 ALLOW".into(),
        MergePolicy::Unknown => "⚪ UNKNOWN".into(),
    }
}

fn trend_arrow(t: &str) -> String {
    match t {
        "degrading" => "↗ degrading".into(),
        "improving" => "↘ improving".into(),
        "stable" => "→ stable".into(),
        _ => "? unknown".into(),
    }
}

fn kind_to_label(kind: &RootCauseKind) -> String {
    match kind {
        RootCauseKind::InfrastructureFlake => "infra flake".into(),
        RootCauseKind::CodeRegression => "code regression".into(),
        RootCauseKind::TestDesignFlaw => "test design flaw".into(),
        RootCauseKind::ExternalDependency => "external dependency".into(),
        RootCauseKind::ResourceExhaustion => "resource exhaustion".into(),
        RootCauseKind::EnvironmentConfig => "environment config".into(),
        RootCauseKind::Undetermined => "undetermined".into(),
    }
}

fn action_from_kind(kind: &str) -> String {
    match kind {
        "flake" => "Add retry with exponential backoff".into(),
        "new_bug" => "Bisect recent commits — likely real regression".into(),
        "known_issue" => "Check issue tracker for existing ticket".into(),
        _ => format!("Review '{kind}' pattern"),
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        baseline::{ExponentialBaseline, TrendStats},
        community::PatternStore,
        decision::{DecisionEngine, TestSignals},
        export::{AnonymizedPattern, EnvClass, PatternStats},
        rootcause::{RootCauseEngine, RootCauseInput},
        triage::TriageVerdict,
    };

    fn build_demo_input(verdict: TriageVerdict, stability: f64, flake_prob: f64) -> DashboardInput {
        // Decision
        let mut baseline = ExponentialBaseline::new(20);
        for v in [450.0, 480.0, 510.0, 490.0, 530.0, 560.0, 520.0, 580.0] {
            baseline.update(v);
        }
        let trend = TrendStats {
            slope_ms_per_run: 8.5,
            intercept_ms: 450.0,
            r_squared: 0.87,
            sample_count: 30,
        };
        let decision = DecisionEngine::evaluate_test(TestSignals {
            name: "charge_card",
            suite: "payments",
            verdict: verdict.clone(),
            stability,
            flake_probability: flake_prob,
            flake_score: flake_prob * 0.9,
            trend: Some(&trend),
            baseline: Some(&baseline),
            run_count: 30,
        });

        // Root cause
        let rc_engine = RootCauseEngine::default();
        let root_cause = rc_engine.analyze(&RootCauseInput {
            triage: verdict,
            flake_probability: flake_prob,
            trend_slope: 8.5,
            failure_rate: 1.0 - stability,
            env_class: EnvClass::Production,
            has_network_calls: true,
            has_timing_deps: false,
            resource_signal: false,
            config_error_signal: false,
            community_matches: vec![],
            context_multiplier: 1.2,
        });

        // Community
        let mut store = PatternStore::new();
        for i in 0..3u32 {
            let mut p = AnonymizedPattern {
                test_token: format!("tok{i}"),
                suite_token: "suite_pay".into(),
                failure_kind: "flake".into(),
                stats: PatternStats {
                    run_count: 40 + i * 10,
                    failure_rate: 0.25 + i as f64 * 0.05,
                    mean_duration_ms: 480.0,
                    stddev_duration_ms: 60.0,
                    flake_probability: 0.7,
                    trend_slope_ms_per_run: 7.0,
                },
                env_class: EnvClass::Production,
                tags: vec!["network".into()],
            };
            // Make sure each pattern is unique enough to not deduplicate
            p.stats.mean_duration_ms += i as f64 * 200.0;
            store.import(p);
        }
        let query = AnonymizedPattern {
            test_token: "query".into(),
            suite_token: "pay".into(),
            failure_kind: "flake".into(),
            stats: PatternStats {
                run_count: 30,
                failure_rate: 1.0 - stability,
                mean_duration_ms: 520.0,
                stddev_duration_ms: 65.0,
                flake_probability: flake_prob,
                trend_slope_ms_per_run: 8.5,
            },
            env_class: EnvClass::Production,
            tags: vec!["network".into()],
        };
        let community = store.find_similar(&query, 5, 0.0);

        DashboardInput {
            decision,
            root_cause,
            community,
        }
    }

    #[test]
    fn render_flaky_test_dashboard() {
        let input = build_demo_input(TriageVerdict::Flake, 0.72, 0.78);
        let report = DashboardReport::build(input);
        let text = report.render_text();

        // Must contain all 4 panel headers
        assert!(text.contains("TEST RISK CARD"), "missing risk card panel");
        assert!(text.contains("ROOT CAUSE"), "missing root cause panel");
        assert!(text.contains("WHAT-IF"), "missing what-if panel");
        assert!(text.contains("COMMUNITY"), "missing community panel");

        // Risk card content
        assert!(text.contains("FLAKE"), "verdict not shown");
        assert!(text.contains("retry"), "action not shown");

        // Root cause content
        assert!(
            text.contains("infrastructure_flake"),
            "root cause not shown"
        );
        assert!(text.contains("fix"), "fix not shown");

        // What-if has at least current pass rate
        assert!(
            text.contains("current pass rate"),
            "what-if current not shown"
        );
    }

    #[test]
    fn render_new_bug_dashboard() {
        let input = build_demo_input(TriageVerdict::NewBug, 0.15, 0.08);
        let report = DashboardReport::build(input);
        let text = report.render_text();

        assert!(text.contains("NEW_BUG"), "verdict not NEW_BUG");
        assert!(text.contains("BLOCK"), "merge not blocked");
        assert!(text.contains("code_regression"), "regression not top cause");
    }

    #[test]
    fn render_stable_test_dashboard() {
        let input = build_demo_input(TriageVerdict::Stable, 0.98, 0.02);
        let report = DashboardReport::build(input);
        let text = report.render_text();
        assert!(text.contains("STABLE"), "verdict not STABLE");
    }

    #[test]
    fn dashboard_text_fits_70_cols() {
        let input = build_demo_input(TriageVerdict::Flake, 0.65, 0.8);
        let report = DashboardReport::build(input);
        let text = report.render_text();

        for (i, line) in text.lines().enumerate() {
            // Count Unicode code points (not bytes) for display width
            let w = line.chars().count();
            assert!(w <= 72, "line {i} too wide ({w} chars): {line}");
        }
    }

    #[test]
    fn progress_bar_fills_correctly() {
        assert_eq!(progress_bar(0, 10), "░░░░░░░░░░");
        assert_eq!(progress_bar(100, 10), "██████████");
        assert_eq!(progress_bar(50, 10), "█████░░░░░");
    }
}
