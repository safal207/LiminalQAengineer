//! Example smoke test demonstrating LIMINAL philosophy

use anyhow::Result;
use async_trait::async_trait;
use liminalqa_core::{entities::Signal, temporal::BiTemporalTime, types::*};
use liminalqa_runner::{
    conavigation::{CoNavigator, NavigationResult, Navigable},
    council::InnerCouncil,
    guidance::{Guidance, GuidanceCategory, Observable},
    runner::{TestCase, TestRunner},
};

struct LoginTest;

#[async_trait]
impl TestCase for LoginTest {
    fn name(&self) -> &str {
        "test_user_login"
    }

    fn suite(&self) -> &str {
        "auth"
    }

    fn guidance(&self) -> Guidance {
        Guidance::new("User should be able to log in with valid credentials")
            .with_observable(Observable::UiVisible {
                selector: "#login-button".to_string(),
            })
            .with_observable(Observable::ApiStatus {
                endpoint: "/api/auth/login".to_string(),
                status: 200,
            })
            .with_timeout(10_000)
            .with_category(GuidanceCategory::HappyPath)
    }

    async fn execute(&self, navigator: &CoNavigator, council: &mut InnerCouncil) -> Result<()> {
        let run_id = new_entity_id();
        let test_id = new_entity_id();

        // Simulate UI interaction
        let ui_signal = Signal {
            id: new_entity_id(),
            run_id,
            test_id,
            signal_type: SignalType::UI,
            timestamp: chrono::Utc::now(),
            latency_ms: Some(50),
            payload_ref: None,
            metadata: serde_json::json!({
                "action": "click",
                "selector": "#login-button"
            })
            .as_object()
            .unwrap()
            .clone(),
            created_at: BiTemporalTime::now(),
        };
        council.record(ui_signal);

        // Simulate API call with retry
        let api_call = || async {
            // Simulate API latency
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
            Ok(())
        };

        navigator.execute_with_retry(api_call).await?;

        let api_signal = Signal {
            id: new_entity_id(),
            run_id,
            test_id,
            signal_type: SignalType::API,
            timestamp: chrono::Utc::now(),
            latency_ms: Some(100),
            payload_ref: None,
            metadata: serde_json::json!({
                "method": "POST",
                "endpoint": "/api/auth/login",
                "status": 200
            })
            .as_object()
            .unwrap()
            .clone(),
            created_at: BiTemporalTime::now(),
        };
        council.record(api_signal);

        Ok(())
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    println!("🧪 Running smoke test example\n");

    let run_id = new_entity_id();
    let runner = TestRunner::new(run_id);

    let test = LoginTest;
    let result = runner.execute(&test).await?;

    println!("✅ Test: {}", result.test.name);
    println!("   Status: {:?}", result.test.status);
    println!("   Duration: {}ms", result.test.duration_ms);
    println!("   Signals: {}", result.signals.len());

    println!("\n📊 Reflection:");
    println!("   Guidance: {}", result.reflection.guidance);
    println!("   Outcome: {:?}", result.reflection.outcome);

    if let Some(reconciliation) = &result.reflection.reconciliation {
        println!("\n🔍 Signal Reconciliation:");
        println!("   Total signals: {}", reconciliation.total_signals);
        for (signal_type, count) in &reconciliation.by_type {
            println!("   {:?}: {}", signal_type, count);
        }

        if !reconciliation.patterns.is_empty() {
            println!("\n⚠️  Patterns detected:");
            for pattern in &reconciliation.patterns {
                println!("   • {}", pattern);
            }
        }
    }

    println!("\n💡 Insights:");
    for insight in &result.reflection.insights {
        println!("   • {}", insight);
    }

    Ok(())
}
