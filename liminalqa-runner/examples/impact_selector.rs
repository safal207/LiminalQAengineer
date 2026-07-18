use liminalqa_runner::{Criticality, ImpactRule, ImpactSelector, TestDescriptor};

fn main() -> anyhow::Result<()> {
    let changed_paths = vec![
        "services/auth/src/token.rs".to_string(),
        "web/src/session/login.ts".to_string(),
    ];

    let catalog = vec![
        TestDescriptor {
            name: "auth/token_refresh".to_string(),
            suite: "api".to_string(),
            rules: vec![ImpactRule::PathPrefix("services/auth/".to_string())],
            criticality: Criticality::Critical,
            recent_failure_rate: 0.18,
            flake_probability: 0.02,
            average_duration_ms: 1_400,
            smoke: false,
        },
        TestDescriptor {
            name: "login/session_restore".to_string(),
            suite: "ui".to_string(),
            rules: vec![
                ImpactRule::PathPrefix("web/src/session/".to_string()),
                ImpactRule::PathContains("login".to_string()),
            ],
            criticality: Criticality::High,
            recent_failure_rate: 0.08,
            flake_probability: 0.05,
            average_duration_ms: 4_200,
            smoke: true,
        },
        TestDescriptor {
            name: "orders/create_limit_order".to_string(),
            suite: "trading".to_string(),
            rules: vec![ImpactRule::PathPrefix("services/orders/".to_string())],
            criticality: Criticality::Critical,
            recent_failure_rate: 0.03,
            flake_probability: 0.01,
            average_duration_ms: 2_100,
            smoke: false,
        },
    ];

    let plan = ImpactSelector::default().select(&changed_paths, &catalog);
    println!("{}", serde_json::to_string_pretty(&plan)?);

    Ok(())
}
