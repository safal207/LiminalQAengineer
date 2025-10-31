//! Database queries for report data

use anyhow::{Context, Result};
use liminalqa_core::report::*;
use sqlx::PgPool;
use tracing::debug;
use uuid::Uuid;

pub async fn build_report(pool: &PgPool, run_id: Uuid) -> Result<ReflectionReport> {
    debug!("Building report for run {}", run_id);

    // Get run metadata
    let run_row = sqlx::query!(
        r#"
        select plan_name, started_at, ended_at
        from run
        where run_id = $1
        "#,
        run_id
    )
    .fetch_one(pool)
    .await
    .context("Failed to fetch run metadata")?;

    // Get test summary
    let summary = get_test_summary(pool, run_id).await?;

    // Get timeline
    let timeline = get_timeline(pool, run_id).await?;

    // Get top slow tests
    let top_slow_tests = get_top_slow_tests(pool, run_id).await?;

    // Get causality trails
    let causality_trails = get_causality_trails(pool, run_id).await?;

    Ok(ReflectionReport {
        run_id: run_id.to_string(),
        plan_name: run_row.plan_name,
        started_at: run_row.started_at,
        ended_at: run_row.ended_at,
        summary,
        timeline,
        top_slow_tests,
        causality_trails,
    })
}

async fn get_test_summary(pool: &PgPool, run_id: Uuid) -> Result<TestSummary> {
    let rows = sqlx::query!(
        r#"
        select status as "status!: String", count(*) as "count!"
        from test_fact
        where run_id = $1 and valid_to = 'infinity'
        group by status
        "#,
        run_id
    )
    .fetch_all(pool)
    .await?;

    let mut summary = TestSummary {
        total: 0,
        passed: 0,
        failed: 0,
        flake: 0,
        timeout: 0,
        skip: 0,
    };

    for row in rows {
        summary.total += row.count;
        match row.status.as_str() {
            "pass" => summary.passed = row.count,
            "fail" => summary.failed = row.count,
            "flake" => summary.flake = row.count,
            "timeout" => summary.timeout = row.count,
            "skip" => summary.skip = row.count,
            _ => {}
        }
    }

    Ok(summary)
}

async fn get_timeline(pool: &PgPool, run_id: Uuid) -> Result<Vec<TimelineBucket>> {
    let rows = sqlx::query!(
        r#"
        select
            date_trunc('minute', valid_from) as "bucket!",
            status as "status!: String",
            count(*) as "count!"
        from test_fact
        where run_id = $1 and valid_to = 'infinity'
        group by 1, 2
        order by 1, 2
        "#,
        run_id
    )
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|row| TimelineBucket {
            bucket: row.bucket,
            status: row.status,
            count: row.count,
        })
        .collect())
}

async fn get_top_slow_tests(pool: &PgPool, run_id: Uuid) -> Result<Vec<SlowTest>> {
    let rows = sqlx::query!(
        r#"
        select test_name, suite, duration_ms, status as "status!: String"
        from test_fact
        where run_id = $1 and valid_to = 'infinity'
        order by duration_ms desc nulls last
        limit 10
        "#,
        run_id
    )
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|row| SlowTest {
            name: row.test_name,
            suite: row.suite,
            duration_ms: row.duration_ms.unwrap_or(0),
            status: row.status,
        })
        .collect())
}

async fn get_causality_trails(pool: &PgPool, run_id: Uuid) -> Result<Vec<CausalityTrail>> {
    let rows = sqlx::query!(
        r#"
        select
            test_name,
            test_failed_at,
            signal_kind as "signal_kind!: String",
            signal_at,
            signal_value,
            signal_meta,
            time_diff_seconds
        from causality_walk($1)
        "#,
        run_id
    )
    .fetch_all(pool)
    .await?;

    // Group by test name
    let mut trails: std::collections::HashMap<String, CausalityTrail> =
        std::collections::HashMap::new();

    for row in rows {
        let trail = trails.entry(row.test_name.clone()).or_insert(CausalityTrail {
            test_name: row.test_name.clone(),
            test_failed_at: row.test_failed_at,
            signals: vec![],
        });

        trail.signals.push(NearbySignal {
            kind: row.signal_kind,
            at: row.signal_at,
            value: row.signal_value,
            meta: row.signal_meta,
            time_diff_seconds: row.time_diff_seconds,
        });
    }

    Ok(trails.into_values().collect())
}
