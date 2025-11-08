//! PostgreSQL store with bi-temporal operations

use crate::models::{ArtifactDto, RunDto, SignalDto, TestDto};
use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use sqlx::{postgres::PgPoolOptions, PgPool};
use tracing::{debug, error};
use uuid::Uuid;

#[derive(Clone)]
pub struct Store {
    pool: PgPool,
}

impl Store {
    pub async fn new(database_url: &str) -> Result<Self> {
        let pool = PgPoolOptions::new()
            .max_connections(10)
            .connect(database_url)
            .await
            .context("Failed to connect to database")?;

        Ok(Self { pool })
    }

    /// Store a test run
    pub async fn put_run(&self, run: &RunDto) -> Result<()> {
        debug!("Storing run: {}", run.run_id);

        sqlx::query!(
            r#"
            insert into run (run_id, build_id, plan_name, env, started_at, runner_version)
            values ($1, $2, $3, $4, $5, $6)
            on conflict (run_id) do update
            set plan_name = excluded.plan_name,
                env = excluded.env,
                started_at = excluded.started_at,
                runner_version = excluded.runner_version
            "#,
            run.run_id,
            run.build_id,
            run.plan_name,
            run.env,
            run.started_at,
            run.runner_version
        )
        .execute(&self.pool)
        .await
        .context("Failed to insert run")?;

        debug!("Run stored successfully: {}", run.run_id);
        Ok(())
    }

    /// Store tests using bi-temporal upsert
    pub async fn put_tests(
        &self,
        run_id: Uuid,
        tests: &[TestDto],
        valid_from: DateTime<Utc>,
    ) -> Result<()> {
        debug!("Storing {} tests for run: {}", tests.len(), run_id);

        let mut tx = self.pool.begin().await?;

        for test in tests {
            // Call bi-temporal upsert function
            let status_str = test.status.as_str();
            let fact_id = sqlx::query_scalar!(
                r#"
                select upsert_test_fact(
                    $1::uuid,           -- run_id
                    $2::text,           -- test_name
                    $3::text,           -- suite
                    $4::text,           -- guidance
                    $5::test_status,    -- status
                    $6::int,            -- duration_ms
                    $7::jsonb,          -- error
                    $8::timestamptz,    -- started_at
                    $9::timestamptz,    -- completed_at
                    $10::timestamptz    -- valid_from
                ) as fact_id
                "#,
                run_id,
                test.name,
                test.suite,
                test.guidance,
                status_str as _,
                test.duration_ms,
                test.error,
                test.started_at,
                test.completed_at,
                valid_from
            )
            .fetch_one(&mut *tx)
            .await
            .context(format!("Failed to upsert test fact: {}", test.name))?;

            debug!("Test fact created: {} (id: {})", test.name, fact_id);
        }

        tx.commit().await?;

        debug!("All tests stored successfully for run: {}", run_id);
        Ok(())
    }

    /// Store signals
    pub async fn put_signals(&self, run_id: Uuid, signals: &[SignalDto]) -> Result<()> {
        debug!("Storing {} signals for run: {}", signals.len(), run_id);

        let mut tx = self.pool.begin().await?;

        for signal in signals {
            let kind_str = signal.kind.as_str();
            sqlx::query!(
                r#"
                insert into signal (run_id, test_name, kind, latency_ms, value, meta, at)
                values ($1, $2, $3::signal_kind, $4, $5, $6, $7)
                "#,
                run_id,
                signal.test_name,
                kind_str as _,
                signal.latency_ms,
                signal.value,
                signal.meta.as_ref().unwrap_or(&serde_json::json!({})),
                signal.at
            )
            .execute(&mut *tx)
            .await
            .context("Failed to insert signal")?;
        }

        tx.commit().await?;

        debug!("All signals stored successfully for run: {}", run_id);
        Ok(())
    }

    /// Store artifacts
    pub async fn put_artifacts(&self, run_id: Uuid, artifacts: &[ArtifactDto]) -> Result<()> {
        debug!("Storing {} artifacts for run: {}", artifacts.len(), run_id);

        let mut tx = self.pool.begin().await?;

        for artifact in artifacts {
            let kind_str = artifact.kind.as_str();
            sqlx::query!(
                r#"
                insert into artifact (run_id, test_name, kind, path_sha256, path, size_bytes, mime_type)
                values ($1, $2, $3::artifact_kind, $4, $5, $6, $7)
                "#,
                run_id,
                artifact.test_name,
                kind_str as _,
                artifact.path_sha256,
                artifact.path,
                artifact.size_bytes,
                artifact.mime_type
            )
            .execute(&mut *tx)
            .await
            .context("Failed to insert artifact")?;
        }

        tx.commit().await?;

        debug!("All artifacts stored successfully for run: {}", run_id);
        Ok(())
    }
}
