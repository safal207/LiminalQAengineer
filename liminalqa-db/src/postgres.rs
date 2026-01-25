use anyhow::{Context, Result};
use liminalqa_core::{entities::*, types::*};
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use std::time::Duration;
use tracing::{debug, info};

#[derive(Clone)]
pub struct PostgresDB {
    pool: PgPool,
}

impl PostgresDB {
    pub async fn new(connection_string: &str) -> Result<Self> {
        info!("Connecting to PostgreSQL...");
        let pool = PgPoolOptions::new()
            .max_connections(20)
            .acquire_timeout(Duration::from_secs(3))
            .connect(connection_string)
            .await
            .context("Failed to connect to PostgreSQL")?;

        info!("Running migrations...");
        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .context("Failed to run migrations")?;

        Ok(Self { pool })
    }

    pub async fn put_run(&self, run: &Run) -> Result<()> {
        let status_str = match run.status {
            RunStatus::Running => "running",
            RunStatus::Passed => "passed",
            RunStatus::Failed => "failed",
            RunStatus::Error => "error",
        };

        sqlx::query(
            r#"
            INSERT INTO runs (
                id, build_id, plan_name, status, started_at, completed_at,
                environment, metadata, created_at,
                protocol_version, self_resonance_score, world_resonance_score, overall_alignment_score
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                completed_at = EXCLUDED.completed_at,
                metadata = EXCLUDED.metadata,
                self_resonance_score = EXCLUDED.self_resonance_score,
                world_resonance_score = EXCLUDED.world_resonance_score,
                overall_alignment_score = EXCLUDED.overall_alignment_score
            "#
        )
        .bind(run.id.to_string())
        .bind(run.build_id.to_string())
        .bind(&run.plan_name)
        .bind(status_str)
        .bind(run.started_at)
        .bind(run.ended_at)
        .bind(serde_json::to_value(&run.env).unwrap_or_default())
        .bind(serde_json::json!({
            "runner_version": run.runner_version,
            "liminal_os_version": run.liminal_os_version
        }))
        .bind(run.created_at.valid_time)
        .bind(&run.protocol_version)
        .bind(run.self_resonance_score)
        .bind(run.world_resonance_score)
        .bind(run.overall_alignment_score)
        .execute(&self.pool)
        .await?;

        debug!("Stored run: {}", run.id);
        Ok(())
    }

    pub async fn put_test(&self, test: &Test) -> Result<()> {
        let metrics = test.protocol_metrics.as_ref();

        let status_str = match test.status {
            TestStatus::Pass => "passed",
            TestStatus::Fail => "failed",
            TestStatus::XFail => "xfail",
            TestStatus::Flake => "flake",
            TestStatus::Timeout => "timeout",
            TestStatus::Skip => "skipped",
        };

        let resonance_frequency = metrics
            .and_then(|m| m.resonance_frequency)
            .map(|v| match v {
                Frequency::High => "high",
                Frequency::Centered => "centered",
                Frequency::Low => "low",
            });

        let readiness_state = metrics.and_then(|m| m.readiness_state).map(|v| match v {
            ReadinessState::Aligned => "aligned",
            ReadinessState::Checking => "checking",
            ReadinessState::Misaligned => "misaligned",
        });

        let internal_direction = metrics.and_then(|m| m.internal_direction).map(|v| match v {
            InternalDirection::Aligned => "aligned",
            InternalDirection::Exploring => "exploring",
            InternalDirection::Reactive => "reactive",
        });

        let alignment_status = metrics.and_then(|m| m.alignment_status).map(|v| match v {
            AlignmentStatus::Aligned => "aligned",
            AlignmentStatus::Checking => "checking",
            AlignmentStatus::Illusion => "illusion",
        });

        sqlx::query(
            r#"
            INSERT INTO tests (
                id, run_id, name, suite, status, duration_ms,
                error_message, stack_trace, executed_at, created_at,

                -- Phase 5 Fields
                self_resonance_score, intent_clarity, resonance_frequency, readiness_state,
                resonating_elements, filtered_noise,
                axis_centered, internal_direction,
                transition_smoothness, resonance_preserved,
                step_from_center, energy_efficiency, energy_waste,
                trajectory_reality, alignment_status, path_pattern,
                world_resonance_score, mutual_influence, feedback_count, learning_count, learnings,
                protocol_cycle_valid, protocol_validation_errors
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10,

                $11, $12, $13, $14,
                $15, $16,
                $17, $18,
                $19, $20,
                $21, $22, $23,
                $24, $25, $26,
                $27, $28, $29, $30, $31,
                $32, $33
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                duration_ms = EXCLUDED.duration_ms,
                error_message = EXCLUDED.error_message,
                self_resonance_score = EXCLUDED.self_resonance_score
            "#,
        )
        .bind(test.id.to_string())
        .bind(test.run_id.to_string())
        .bind(&test.name)
        .bind(&test.suite)
        .bind(status_str)
        .bind(test.duration_ms as i32)
        .bind(test.error.as_ref().map(|e| e.message.clone()))
        .bind(test.error.as_ref().and_then(|e| e.stack_trace.clone()))
        .bind(test.started_at)
        .bind(test.created_at.valid_time)
        // Phase 5
        .bind(metrics.and_then(|m| m.self_resonance_score.map(|v| v as f32)))
        .bind(metrics.and_then(|m| m.intent_clarity.clone()))
        .bind(resonance_frequency)
        .bind(readiness_state)
        .bind(metrics.and_then(|m| m.resonating_elements.clone()))
        .bind(metrics.and_then(|m| m.filtered_noise.clone()))
        .bind(metrics.and_then(|m| m.axis_centered))
        .bind(internal_direction)
        .bind(metrics.and_then(|m| m.transition_smoothness.map(|v| v as f32)))
        .bind(metrics.and_then(|m| m.resonance_preserved))
        .bind(metrics.and_then(|m| m.step_from_center))
        .bind(metrics.and_then(|m| m.energy_efficiency.map(|v| v as f32)))
        .bind(metrics.and_then(|m| m.energy_waste.map(|v| v as f32)))
        .bind(metrics.and_then(|m| m.trajectory_reality))
        .bind(alignment_status)
        .bind(metrics.and_then(|m| m.path_pattern.clone()))
        .bind(metrics.and_then(|m| m.world_resonance_score.map(|v| v as f32)))
        .bind(metrics.and_then(|m| m.mutual_influence))
        .bind(metrics.and_then(|m| m.feedback_count))
        .bind(metrics.and_then(|m| m.learning_count))
        .bind(metrics.and_then(|m| m.learnings.clone()))
        .bind(metrics.and_then(|m| m.protocol_cycle_valid))
        .bind(metrics.and_then(|m| m.protocol_validation_errors.clone()))
        .execute(&self.pool)
        .await?;

        debug!("Stored test: {}", test.id);
        Ok(())
    }

    pub async fn put_signal(&self, signal: &Signal) -> Result<()> {
        let signal_type_str = match signal.signal_type {
            SignalType::UI => "ui",
            SignalType::API => "api",
            SignalType::WebSocket => "websocket",
            SignalType::GRPC => "grpc",
            SignalType::Database => "database",
            SignalType::Network => "network",
            SignalType::System => "system",
        };

        sqlx::query(
            r#"
            INSERT INTO signals (
                id, test_id, signal_type, timestamp, value, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            "#,
        )
        .bind(signal.id.to_string())
        .bind(signal.test_id.to_string())
        .bind(signal_type_str)
        .bind(signal.timestamp)
        .bind(&signal.value)
        .bind(serde_json::to_value(&signal.metadata).unwrap_or_default())
        .bind(signal.created_at.valid_time)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn put_artifact(&self, artifact: &Artifact) -> Result<()> {
        let artifact_type_str = match artifact.artifact_type {
            ArtifactType::Screenshot => "screenshot",
            ArtifactType::ApiResponse => "apiresponse",
            ArtifactType::WsMessage => "wsmessage",
            ArtifactType::GrpcTrace => "grpctrace",
            ArtifactType::Log => "log",
            ArtifactType::Video => "video",
            ArtifactType::Trace => "trace",
        };

        sqlx::query(
            r#"
            INSERT INTO artifacts (
                id, test_id, artifact_type, file_path, content_hash, size_bytes, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            "#
        )
        .bind(artifact.id.to_string())
        .bind(artifact.test_id.to_string())
        .bind(artifact_type_str)
        .bind(&artifact.artifact_ref.path)
        .bind(&artifact.artifact_ref.sha256)
        .bind(artifact.artifact_ref.size_bytes as i64)
        .bind(serde_json::json!({ "mime_type": artifact.artifact_ref.mime_type, "description": artifact.description }))
        .bind(artifact.created_at.valid_time)
        .execute(&self.pool)
        .await?;

        Ok(())
    }
}
