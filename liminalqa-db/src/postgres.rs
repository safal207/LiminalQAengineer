// liminalqa-db/src/postgres.rs

use sqlx::{PgPool, postgres::PgPoolOptions};
use crate::models::*;
use crate::error::Result;
use chrono::{DateTime, Utc};

#[derive(Clone)]
pub struct PostgresStorage {
    pool: PgPool,
}

impl PostgresStorage {
    /// Create new PostgreSQL storage
    pub async fn new(database_url: &str) -> Result<Self> {
        let pool = PgPoolOptions::new()
            .max_connections(20)
            .acquire_timeout(std::time::Duration::from_secs(5))
            .connect(database_url)
            .await?;

        // Run migrations
        sqlx::migrate!("./migrations")
            .run(&pool)
            .await?;

        tracing::info!("PostgreSQL storage initialized");

        Ok(Self { pool })
    }

    // ========================================================================
    // RUNS - Basic operations (Phase 4)
    // ========================================================================

    pub async fn insert_run(&self, run: &TestRun) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO runs (
                id, build_id, plan_name, status,
                started_at, environment, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            "#
        )
        .bind(&run.id)
        .bind(&run.build_id)
        .bind(&run.plan_name)
        .bind(&run.status)
        .bind(run.started_at)
        .bind(&run.environment)
        .bind(&run.metadata)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn get_recent_runs(&self, limit: i64) -> Result<Vec<TestRun>> {
        let runs = sqlx::query_as::<_, TestRun>(
            r#"
            SELECT
                id, build_id, plan_name, status,
                started_at, completed_at, duration_ms,
                environment, metadata, created_at,
                protocol_version, self_resonance_score,
                world_resonance_score, overall_alignment_score
            FROM runs
            ORDER BY started_at DESC
            LIMIT $1
            "#
        )
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;

        Ok(runs)
    }

    // ========================================================================
    // TESTS - Basic operations (Phase 4)
    // ========================================================================

    pub async fn insert_test(&self, test: &TestResult) -> Result<()> {
        // Phase 4: Insert basic fields only
        // Protocol metrics are NULL for now

        sqlx::query(
            r#"
            INSERT INTO tests (
                id, run_id, name, suite, status,
                duration_ms, error_message, stack_trace,
                metadata, executed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#
        )
        .bind(&test.id)
        .bind(&test.run_id)
        .bind(&test.name)
        .bind(&test.suite)
        .bind(&test.status)
        .bind(test.duration_ms)
        .bind(&test.error_message)
        .bind(&test.stack_trace)
        .bind(&test.metadata)
        .bind(test.executed_at)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    /// Phase 5: Insert test with protocol metrics
    pub async fn insert_test_with_protocol(
        &self,
        test: &TestResult,
        metrics: &ProtocolMetrics
    ) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO tests (
                id, run_id, name, suite, status, duration_ms,
                self_resonance_score, energy_efficiency, trajectory_reality,
                world_resonance_score, mutual_influence, learning_count, learnings,
                executed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            "#
        )
        .bind(&test.id)
        .bind(&test.run_id)
        .bind(&test.name)
        .bind(&test.suite)
        .bind(&test.status)
        .bind(test.duration_ms)
        .bind(metrics.self_resonance_score)
        .bind(metrics.energy_efficiency)
        .bind(metrics.trajectory_reality)
        .bind(metrics.world_resonance_score)
        .bind(metrics.mutual_influence)
        .bind(metrics.learning_count)
        .bind(&metrics.learnings)
        .bind(test.executed_at)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn get_tests_by_run(&self, run_id: &str) -> Result<Vec<TestResult>> {
        let tests = sqlx::query_as::<_, TestResult>(
            r#"
            SELECT
                id, run_id, name, suite, status,
                duration_ms, error_message, stack_trace,
                metadata, executed_at, created_at,
                NULL as "protocol_metrics"
            FROM tests
            WHERE run_id = $1
            ORDER BY executed_at
            "#
        )
        .bind(run_id)
        .fetch_all(&self.pool)
        .await?;

        Ok(tests)
    }

    // ========================================================================
    // BASELINES - Drift detection (Phase 4)
    // ========================================================================

    pub async fn upsert_baseline(&self, baseline: &Baseline) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO baselines (
                test_name, suite, mean_duration_ms,
                stddev_duration_ms, sample_size, last_updated
            )
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (test_name, suite)
            DO UPDATE SET
                mean_duration_ms = EXCLUDED.mean_duration_ms,
                stddev_duration_ms = EXCLUDED.stddev_duration_ms,
                sample_size = EXCLUDED.sample_size,
                last_updated = NOW()
            "#
        )
        .bind(&baseline.test_name)
        .bind(&baseline.suite)
        .bind(baseline.mean_duration_ms)
        .bind(baseline.stddev_duration_ms)
        .bind(baseline.sample_size)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn get_baseline(
        &self,
        test_name: &str,
        suite: &str
    ) -> Result<Option<Baseline>> {
        let baseline = sqlx::query_as::<_, Baseline>(
            r#"
            SELECT
                id, test_name, suite, mean_duration_ms,
                stddev_duration_ms, sample_size,
                last_updated, created_at,
                mean_self_resonance, mean_energy_efficiency,
                mean_world_resonance
            FROM baselines
            WHERE test_name = $1 AND suite = $2
            "#
        )
        .bind(test_name)
        .bind(suite)
        .fetch_optional(&self.pool)
        .await?;

        Ok(baseline)
    }

    // ========================================================================
    // DRIFT DATA - For visualization (Phase 4)
    // ========================================================================

    pub async fn get_drift_data(
        &self,
        test_name: &str,
        suite: &str,
        days: i32
    ) -> Result<Vec<DriftDataPoint>> {
        #[derive(sqlx::FromRow)]
        struct RawDriftData {
            timestamp: DateTime<Utc>,
            duration_ms: i32,
            mean_duration_ms: Option<f64>,
            stddev_duration_ms: Option<f64>,
        }

        let raw_data = sqlx::query_as::<_, RawDriftData>(
            r#"
            SELECT
                t.executed_at as timestamp,
                t.duration_ms,
                b.mean_duration_ms,
                b.stddev_duration_ms
            FROM tests t
            LEFT JOIN baselines b ON b.test_name = t.name AND b.suite = t.suite
            WHERE t.name = $1
              AND t.suite = $2
              AND t.executed_at > NOW() - INTERVAL '1 day' * $3
            ORDER BY t.executed_at ASC
            "#
        )
        .bind(test_name)
        .bind(suite)
        .bind(days as f64)
        .fetch_all(&self.pool)
        .await?;

        let data = raw_data.into_iter().map(|d| DriftDataPoint {
            timestamp: d.timestamp,
            duration_ms: d.duration_ms,
            mean_duration_ms: d.mean_duration_ms.unwrap_or(0.0),
            stddev_duration_ms: d.stddev_duration_ms.unwrap_or(0.0),
        }).collect();

        Ok(data)
    }

    // ========================================================================
    // RESONANCE SCORES (Phase 4)
    // ========================================================================

    pub async fn upsert_resonance_score(
        &self,
        score: &ResonanceScore
    ) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO resonance_scores (
                test_name, suite, score, correlated_tests, last_calculated
            )
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (test_name, suite)
            DO UPDATE SET
                score = EXCLUDED.score,
                correlated_tests = EXCLUDED.correlated_tests,
                last_calculated = NOW()
            "#
        )
        .bind(&score.test_name)
        .bind(&score.suite)
        .bind(score.score)
        .bind(&score.correlated_tests)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn get_resonance_scores(&self) -> Result<Vec<ResonanceScore>> {
        let scores = sqlx::query_as::<_, ResonanceScore>(
            r#"
            SELECT
                id, test_name, suite, score,
                correlated_tests, last_calculated, created_at,
                correlation_type, correlation_strength, pattern_description
            FROM resonance_scores
            ORDER BY score DESC
            LIMIT 100
            "#
        )
        .fetch_all(&self.pool)
        .await?;

        Ok(scores)
    }

    // ========================================================================
    // PROTOCOL QUALITY - Phase 5 queries (ready but not used yet)
    // ========================================================================

    pub async fn get_protocol_quality_view(
        &self,
        limit: i64
    ) -> Result<Vec<ProtocolQualityView>> {
        let results = sqlx::query_as::<_, ProtocolQualityView>(
            r#"
            SELECT
                id, name, suite, status, duration_ms,
                self_resonance_score, energy_efficiency,
                trajectory_reality, world_resonance_score,
                mutual_influence, learning_count,
                CASE
                    WHEN self_resonance_score IS NULL THEN NULL
                    ELSE (
                        COALESCE(self_resonance_score, 0.5) * 0.3 +
                        COALESCE(energy_efficiency, 0.5) * 0.2 +
                        COALESCE(world_resonance_score, 0.5) * 0.3 +
                        CASE WHEN trajectory_reality THEN 0.2 ELSE 0 END
                    )
                END as "overall_protocol_quality"
            FROM tests
            WHERE self_resonance_score IS NOT NULL
            ORDER BY executed_at DESC
            LIMIT $1
            "#
        )
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;

        Ok(results)
    }
}
