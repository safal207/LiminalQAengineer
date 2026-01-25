use crate::models::*;
use anyhow::Result;
use sqlx::{postgres::PgPoolOptions, PgPool};

pub struct PostgresStorage {
    pool: PgPool,
}

#[derive(sqlx::FromRow)]
struct TestId {
    id: String,
}

impl PostgresStorage {
    pub async fn new(database_url: &str) -> Result<Self> {
        let pool = PgPoolOptions::new()
            .max_connections(20)
            .connect(database_url)
            .await?;

        // Run migrations
        sqlx::migrate!("./migrations").run(&pool).await?;

        Ok(Self { pool })
    }

    // Insert a new test run
    pub async fn insert_run(&self, run: &TestRun) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO runs (
                id, build_id, plan_name, status,
                started_at, completed_at, duration_ms, environment, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#,
        )
        .bind(&run.id)
        .bind(&run.build_id)
        .bind(&run.plan_name)
        .bind(&run.status)
        .bind(run.started_at)
        .bind(run.completed_at)
        .bind(run.duration_ms)
        .bind(&run.environment)
        .bind(&run.metadata)
        .bind(run.created_at)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    // Insert a test result
    pub async fn insert_test(&self, test: &TestResult) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO tests (
                id, run_id, name, suite, status,
                duration_ms, error_message, stack_trace, metadata, executed_at, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            "#,
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
        .bind(test.created_at)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn insert_signal(&self, signal: &SignalEntity) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO signals (
                id, test_id, signal_type, timestamp, value, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            "#,
        )
        .bind(&signal.id)
        .bind(&signal.test_id)
        .bind(&signal.signal_type)
        .bind(signal.timestamp)
        .bind(&signal.value)
        .bind(&signal.metadata)
        .bind(signal.created_at)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn insert_artifact(&self, artifact: &ArtifactEntity) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO artifacts (
                id, test_id, artifact_type, file_path, content_hash, size_bytes, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            "#
        )
        .bind(&artifact.id)
        .bind(&artifact.test_id)
        .bind(&artifact.artifact_type)
        .bind(&artifact.file_path)
        .bind(&artifact.content_hash)
        .bind(artifact.size_bytes)
        .bind(&artifact.metadata)
        .bind(artifact.created_at)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    // Update or insert baseline
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
            "#,
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

    // Get baseline for a test
    pub async fn get_baseline(&self, test_name: &str, suite: &str) -> Result<Option<Baseline>> {
        let result = sqlx::query_as::<_, Baseline>(
            r#"
            SELECT test_name, suite, mean_duration_ms,
                   stddev_duration_ms, sample_size, last_updated
            FROM baselines
            WHERE test_name = $1 AND suite = $2
            "#,
        )
        .bind(test_name)
        .bind(suite)
        .fetch_optional(&self.pool)
        .await?;

        Ok(result)
    }

    // Get recent test runs
    pub async fn get_recent_runs(&self, limit: i64) -> Result<Vec<TestRun>> {
        let runs = sqlx::query_as::<_, TestRun>(
            r#"
            SELECT id, build_id, plan_name, status,
                   started_at, completed_at, duration_ms,
                   environment, metadata, created_at
            FROM runs
            ORDER BY started_at DESC
            LIMIT $1
            "#,
        )
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;

        Ok(runs)
    }

    // Get drift data for visualization
    pub async fn get_drift_data(
        &self,
        test_name: &str,
        suite: &str,
        days: i32,
    ) -> Result<Vec<DriftDataPoint>> {
        let data = sqlx::query_as::<_, DriftDataPoint>(
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
            "#,
        )
        .bind(test_name)
        .bind(suite)
        .bind(days as f64)
        .fetch_all(&self.pool)
        .await?;

        Ok(data)
    }

    // Get resonance scores
    pub async fn get_resonance_scores(&self) -> Result<Vec<ResonanceScore>> {
        let scores = sqlx::query_as::<_, ResonanceScore>(
            r#"
            SELECT test_name, suite, score, correlated_tests, last_calculated
            FROM resonance_scores
            ORDER BY score DESC
            LIMIT 100
            "#,
        )
        .fetch_all(&self.pool)
        .await?;

        Ok(scores)
    }

    pub async fn upsert_resonance_score(&self, score: &ResonanceScore) -> Result<()> {
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
            "#,
        )
        .bind(&score.test_name)
        .bind(&score.suite)
        .bind(score.score)
        .bind(&score.correlated_tests)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn find_test_by_name(&self, run_id: &str, test_name: &str) -> Result<Option<String>> {
        let result = sqlx::query_as::<_, TestId>(
            r#"
            SELECT id FROM tests WHERE run_id = $1 AND name = $2 LIMIT 1
            "#,
        )
        .bind(run_id)
        .bind(test_name)
        .fetch_optional(&self.pool)
        .await?;

        Ok(result.map(|r| r.id))
    }

    pub async fn get_test_history(
        &self,
        name: &str,
        suite: &str,
        limit: i64,
    ) -> Result<Vec<TestResult>> {
        let tests = sqlx::query_as::<_, TestResult>(
            r#"
            SELECT id, run_id, name, suite, status,
                duration_ms, error_message, stack_trace, metadata, executed_at, created_at
            FROM tests
            WHERE name = $1 AND suite = $2
            ORDER BY executed_at DESC
            LIMIT $3
            "#,
        )
        .bind(name)
        .bind(suite)
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;

        Ok(tests)
    }

    pub async fn flush(&self) -> Result<()> {
        // Postgres writes are immediate, but we keep this method for compatibility if needed.
        Ok(())
    }
}
