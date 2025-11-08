//! Ingest layer: send test data to storage

use anyhow::{Context, Result};
use async_trait::async_trait;
use liminalqa_core::{entities::*, types::*};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tracing::{debug, info};

/// Ingest mode configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "mode")]
pub enum IngestConfig {
    /// File-system based (local development)
    #[serde(rename = "fs")]
    Fs { root: PathBuf },
    /// HTTP-based (production)
    #[serde(rename = "http")]
    Http { url: String, token: String },
}

impl Default for IngestConfig {
    fn default() -> Self {
        Self::Fs {
            root: PathBuf::from("/var/liminal/runs"),
        }
    }
}

/// Unified ingest interface
#[async_trait]
pub trait Ingest: Send + Sync {
    async fn put_run(&self, run: &Run) -> Result<()>;
    async fn put_tests(&self, tests: &[Test]) -> Result<()>;
    async fn put_signals(&self, signals: &[Signal]) -> Result<()>;
    async fn put_artifacts(&self, artifacts: &[Artifact]) -> Result<()>;
}

/// Create ingest from config
pub fn create_ingest(config: IngestConfig) -> Box<dyn Ingest> {
    match config {
        IngestConfig::Fs { root } => Box::new(IngestFs::new(root)),
        IngestConfig::Http { url, token } => Box::new(IngestHttp::new(url, token)),
    }
}

// --- File-system ingest ---

pub struct IngestFs {
    root: PathBuf,
}

impl IngestFs {
    pub fn new(root: PathBuf) -> Self {
        Self { root }
    }

    fn write_json<T: Serialize>(&self, run_id: &EntityId, name: &str, value: &T) -> Result<()> {
        let dir = self.root.join(run_id.to_string());
        std::fs::create_dir_all(&dir)?;
        let path = dir.join(name);
        let json = serde_json::to_string_pretty(value)?;
        std::fs::write(&path, json)?;
        debug!("Wrote {} to {:?}", name, path);
        Ok(())
    }
}

#[async_trait]
impl Ingest for IngestFs {
    async fn put_run(&self, run: &Run) -> Result<()> {
        self.write_json(&run.id, "run.json", run)
    }

    async fn put_tests(&self, tests: &[Test]) -> Result<()> {
        if tests.is_empty() {
            return Ok(());
        }
        let run_id = tests[0].run_id;
        self.write_json(&run_id, "tests.json", &tests)
    }

    async fn put_signals(&self, signals: &[Signal]) -> Result<()> {
        if signals.is_empty() {
            return Ok(());
        }
        let run_id = signals[0].run_id;
        self.write_json(&run_id, "signals.json", &signals)
    }

    async fn put_artifacts(&self, artifacts: &[Artifact]) -> Result<()> {
        if artifacts.is_empty() {
            return Ok(());
        }
        let run_id = artifacts[0].run_id;
        self.write_json(&run_id, "artifacts.json", &artifacts)
    }
}

// --- HTTP ingest ---

pub struct IngestHttp {
    url: String,
    token: String,
    client: reqwest::Client,
    max_retries: u32,
}

impl IngestHttp {
    pub fn new(url: String, token: String) -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(15))
            .connect_timeout(std::time::Duration::from_secs(5))
            .pool_max_idle_per_host(10)
            .build()
            .expect("Failed to create HTTP client");

        Self {
            url,
            token,
            client,
            max_retries: 3,
        }
    }

    fn is_retryable_error(status: reqwest::StatusCode) -> bool {
        // Retry on 5xx server errors and 429 rate limiting
        status.is_server_error() || status == reqwest::StatusCode::TOO_MANY_REQUESTS
    }

    async fn post<T: Serialize>(&self, endpoint: &str, body: &T) -> Result<()> {
        let url = format!("{}{}", self.url, endpoint);
        let mut attempt = 0;

        loop {
            attempt += 1;
            debug!("POST {} (attempt {}/{})", url, attempt, self.max_retries + 1);

            let resp = match self
                .client
                .post(&url)
                .header("Authorization", format!("Bearer {}", self.token))
                .json(body)
                .send()
                .await
            {
                Ok(r) => r,
                Err(e) if attempt <= self.max_retries => {
                    let backoff_ms = 2u64.pow(attempt - 1) * 1000; // Exponential: 1s, 2s, 4s
                    debug!("Request failed: {}. Retrying in {}ms...", e, backoff_ms);
                    tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                    continue;
                }
                Err(e) => {
                    return Err(e).context(format!("Failed to POST {} after {} attempts", endpoint, attempt));
                }
            };

            let status = resp.status();

            // Check if we should retry
            if !status.is_success() {
                let text = resp.text().await.unwrap_or_default();

                if Self::is_retryable_error(status) && attempt <= self.max_retries {
                    let backoff_ms = 2u64.pow(attempt - 1) * 1000;
                    debug!("HTTP {} {}. Retrying in {}ms...", status, endpoint, backoff_ms);
                    tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                    continue;
                } else {
                    anyhow::bail!("HTTP {} {}: {}", status, endpoint, text);
                }
            }

            // Success - parse response
            let result: serde_json::Value = resp.json().await?;
            if !result.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
                let error = result
                    .get("error")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown error");
                anyhow::bail!("Ingest failed: {}", error);
            }

            debug!("POST {} succeeded (attempt {})", endpoint, attempt);
            return Ok(());
        }
    }
}

#[async_trait]
impl Ingest for IngestHttp {
    async fn put_run(&self, run: &Run) -> Result<()> {
        #[derive(Serialize)]
        struct RunDto {
            run_id: EntityId,
            build_id: Option<EntityId>,
            plan_name: String,
            env: serde_json::Value,
            started_at: chrono::DateTime<chrono::Utc>,
            runner_version: Option<String>,
        }

        let dto = RunDto {
            run_id: run.id,
            build_id: Some(run.build_id),
            plan_name: run.plan_name.clone(),
            env: serde_json::to_value(&run.env)?,
            started_at: run.started_at,
            runner_version: Some(run.runner_version.clone()),
        };

        self.post("/ingest/run", &dto).await
    }

    async fn put_tests(&self, tests: &[Test]) -> Result<()> {
        if tests.is_empty() {
            return Ok(());
        }

        #[derive(Serialize)]
        struct TestsDto {
            run_id: EntityId,
            tests: Vec<TestDtoItem>,
            valid_from: chrono::DateTime<chrono::Utc>,
        }

        #[derive(Serialize)]
        struct TestDtoItem {
            name: String,
            suite: String,
            guidance: Option<String>,
            status: String,
            duration_ms: Option<i32>,
            error: Option<serde_json::Value>,
            started_at: Option<chrono::DateTime<chrono::Utc>>,
            completed_at: Option<chrono::DateTime<chrono::Utc>>,
        }

        let run_id = tests[0].run_id;
        let items: Vec<TestDtoItem> = tests
            .iter()
            .map(|t| TestDtoItem {
                name: t.name.clone(),
                suite: t.suite.clone(),
                guidance: Some(t.guidance.clone()),
                status: format!("{:?}", t.status).to_lowercase(),
                duration_ms: Some(t.duration_ms as i32),
                error: t.error.as_ref().map(|e| serde_json::to_value(e).unwrap()),
                started_at: Some(t.started_at),
                completed_at: Some(t.completed_at),
            })
            .collect();

        let dto = TestsDto {
            run_id,
            tests: items,
            valid_from: chrono::Utc::now(),
        };

        self.post("/ingest/tests", &dto).await
    }

    async fn put_signals(&self, signals: &[Signal]) -> Result<()> {
        if signals.is_empty() {
            return Ok(());
        }

        #[derive(Serialize)]
        struct SignalsDto {
            run_id: EntityId,
            signals: Vec<SignalDtoItem>,
        }

        #[derive(Serialize)]
        struct SignalDtoItem {
            test_name: Option<String>,
            kind: String,
            latency_ms: Option<i32>,
            value: Option<f64>,
            meta: Option<serde_json::Value>,
            at: chrono::DateTime<chrono::Utc>,
        }

        let run_id = signals[0].run_id;
        let items: Vec<SignalDtoItem> = signals
            .iter()
            .map(|s| SignalDtoItem {
                test_name: None, // TODO: track test name
                kind: format!("{:?}", s.signal_type).to_lowercase(),
                latency_ms: s.latency_ms.map(|v| v as i32),
                value: None,
                meta: Some(serde_json::to_value(&s.metadata).unwrap()),
                at: s.timestamp,
            })
            .collect();

        let dto = SignalsDto {
            run_id,
            signals: items,
        };

        self.post("/ingest/signals", &dto).await
    }

    async fn put_artifacts(&self, artifacts: &[Artifact]) -> Result<()> {
        if artifacts.is_empty() {
            return Ok(());
        }

        #[derive(Serialize)]
        struct ArtifactsDto {
            run_id: EntityId,
            artifacts: Vec<ArtifactDtoItem>,
        }

        #[derive(Serialize)]
        struct ArtifactDtoItem {
            test_name: Option<String>,
            kind: String,
            path_sha256: String,
            path: String,
            size_bytes: Option<i64>,
            mime_type: Option<String>,
        }

        let run_id = artifacts[0].run_id;
        let items: Vec<ArtifactDtoItem> = artifacts
            .iter()
            .map(|a| ArtifactDtoItem {
                test_name: None, // TODO: track test name
                kind: format!("{:?}", a.artifact_type).to_lowercase(),
                path_sha256: a.artifact_ref.sha256.clone(),
                path: a.artifact_ref.path.clone(),
                size_bytes: Some(a.artifact_ref.size_bytes as i64),
                mime_type: a.artifact_ref.mime_type.clone(),
            })
            .collect();

        let dto = ArtifactsDto {
            run_id,
            artifacts: items,
        };

        self.post("/ingest/artifacts", &dto).await
    }
}
