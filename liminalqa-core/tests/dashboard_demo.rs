//! Dashboard demo — renders all 4 panels for 3 realistic test scenarios.
//!
//! Run with:
//!
//! ```bash
//! cargo test -p liminalqa-core --test dashboard_demo -- --nocapture
//! ```
//!
//! The output is designed to be:
//! - Screenshottable for README / blog posts
//! - Pasteable into a GitHub comment
//! - GIF-recordable with `asciinema`

use liminalqa_core::{
    baseline::{ExponentialBaseline, TrendStats},
    community::PatternStore,
    dashboard::{DashboardInput, DashboardReport},
    decision::{DecisionEngine, TestSignals},
    export::{AnonymizedPattern, EnvClass, PatternStats},
    rootcause::{RootCauseEngine, RootCauseInput},
    triage::TriageVerdict,
};

// ---------------------------------------------------------------------------
// Scenario 1 — Flaky payment test (most common real-world case)
// ---------------------------------------------------------------------------

#[test]
fn scenario_flaky_network_test() {
    println!("\n{}", "═".repeat(70));
    println!("  SCENARIO 1: Flaky network test  (payments/charge_card)");
    println!("{}\n", "═".repeat(70));

    // 30-run history with gradual degradation
    let mut baseline = ExponentialBaseline::new(20);
    for ms in [
        440.0, 460.0, 455.0, 490.0, 510.0, 480.0, 530.0, 520.0, 560.0, 580.0, 595.0, 610.0,
    ] {
        baseline.update(ms);
    }
    let trend = TrendStats {
        slope_ms_per_run: 9.2,
        intercept_ms: 440.0,
        r_squared: 0.89,
        sample_count: 30,
    };

    let decision = DecisionEngine::evaluate_test(TestSignals {
        name: "charge_card",
        suite: "payments",
        verdict: TriageVerdict::Flake,
        stability: 0.70,
        flake_probability: 0.82,
        flake_score: 0.75,
        trend: Some(&trend),
        baseline: Some(&baseline),
        run_count: 30,
    });

    let rc = RootCauseEngine::default().analyze(&RootCauseInput {
        triage: TriageVerdict::Flake,
        flake_probability: 0.82,
        trend_slope: 9.2,
        failure_rate: 0.30,
        env_class: EnvClass::Production,
        has_network_calls: true,
        has_timing_deps: false,
        resource_signal: false,
        config_error_signal: false,
        community_matches: vec![],
        context_multiplier: 1.3,
    });

    let community = make_community_store(0.72, 0.80, EnvClass::Production, "flake");

    let input = DashboardInput {
        decision,
        root_cause: rc,
        community,
    };
    let report = DashboardReport::build(input);
    println!("{}", report.render_text());
}

// ---------------------------------------------------------------------------
// Scenario 2 — New regression in auth service
// ---------------------------------------------------------------------------

#[test]
fn scenario_new_regression() {
    println!("\n{}", "═".repeat(70));
    println!("  SCENARIO 2: New regression  (auth/verify_token)");
    println!("{}\n", "═".repeat(70));

    // Was stable, now failing consistently
    let mut baseline = ExponentialBaseline::new(20);
    for ms in [80.0, 82.0, 79.0, 83.0, 81.0, 80.0, 82.0, 78.0] {
        baseline.update(ms);
    }
    let trend = TrendStats {
        slope_ms_per_run: 1.1,
        intercept_ms: 80.0,
        r_squared: 0.55,
        sample_count: 25,
    };

    let decision = DecisionEngine::evaluate_test(TestSignals {
        name: "verify_token",
        suite: "auth",
        verdict: TriageVerdict::NewBug,
        stability: 0.10,
        flake_probability: 0.05,
        flake_score: 0.04,
        trend: Some(&trend),
        baseline: Some(&baseline),
        run_count: 25,
    });

    let rc = RootCauseEngine::default().analyze(&RootCauseInput {
        triage: TriageVerdict::NewBug,
        flake_probability: 0.05,
        trend_slope: 1.1,
        failure_rate: 0.90,
        env_class: EnvClass::Production,
        has_network_calls: false,
        has_timing_deps: false,
        resource_signal: false,
        config_error_signal: false,
        community_matches: vec![],
        context_multiplier: 1.5,
    });

    let community = make_community_store(0.08, 0.05, EnvClass::Production, "new_bug");

    let input = DashboardInput {
        decision,
        root_cause: rc,
        community,
    };
    let report = DashboardReport::build(input);
    println!("{}", report.render_text());
}

// ---------------------------------------------------------------------------
// Scenario 3 — Rock-solid test, safe to skip
// ---------------------------------------------------------------------------

#[test]
fn scenario_stable_skippable() {
    println!("\n{}", "═".repeat(70));
    println!("  SCENARIO 3: Stable test — safe to skip  (db/connection_pool)");
    println!("{}\n", "═".repeat(70));

    let mut baseline = ExponentialBaseline::new(20);
    for ms in [
        12.0, 11.0, 13.0, 12.0, 11.0, 12.0, 13.0, 12.0, 11.0, 12.0, 13.0, 12.0, 11.0, 12.0, 13.0,
        12.0,
    ] {
        baseline.update(ms);
    }
    let trend = TrendStats {
        slope_ms_per_run: 0.05,
        intercept_ms: 12.0,
        r_squared: 0.02,
        sample_count: 100,
    };

    let decision = DecisionEngine::evaluate_test(TestSignals {
        name: "connection_pool",
        suite: "db",
        verdict: TriageVerdict::Stable,
        stability: 1.0,
        flake_probability: 0.01,
        flake_score: 0.01,
        trend: Some(&trend),
        baseline: Some(&baseline),
        run_count: 100,
    });

    let rc = RootCauseEngine::default().analyze(&RootCauseInput {
        triage: TriageVerdict::Stable,
        flake_probability: 0.01,
        trend_slope: 0.05,
        failure_rate: 0.0,
        env_class: EnvClass::Ci,
        has_network_calls: false,
        has_timing_deps: false,
        resource_signal: false,
        config_error_signal: false,
        community_matches: vec![],
        context_multiplier: 1.0,
    });

    let input = DashboardInput {
        decision,
        root_cause: rc,
        community: vec![],
    };
    let report = DashboardReport::build(input);
    println!("{}", report.render_text());
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn make_community_store(
    failure_rate: f64,
    flake_prob: f64,
    env: EnvClass,
    kind: &str,
) -> Vec<liminalqa_core::community::SimilarityMatch> {
    let mut store = PatternStore::new();
    // Add 4 community patterns with slight variations
    let durations = [480.0_f64, 700.0, 950.0, 1200.0];
    for (i, dur) in durations.iter().enumerate() {
        let p = AnonymizedPattern {
            test_token: format!("comm_tok_{i}"),
            suite_token: "comm_suite".into(),
            failure_kind: kind.into(),
            stats: PatternStats {
                run_count: 50 + i as u32 * 15,
                failure_rate: failure_rate + i as f64 * 0.03,
                mean_duration_ms: *dur,
                stddev_duration_ms: dur * 0.12,
                flake_probability: flake_prob,
                trend_slope_ms_per_run: 7.0 + i as f64 * 2.0,
            },
            env_class: env.clone(),
            tags: vec!["network".into()],
        };
        store.import(p);
    }
    let query = AnonymizedPattern {
        test_token: "query".into(),
        suite_token: "query_suite".into(),
        failure_kind: kind.into(),
        stats: PatternStats {
            run_count: 30,
            failure_rate,
            mean_duration_ms: 520.0,
            stddev_duration_ms: 65.0,
            flake_probability: flake_prob,
            trend_slope_ms_per_run: 9.0,
        },
        env_class: env,
        tags: vec!["network".into()],
    };
    store.find_similar(&query, 3, 0.0)
}
