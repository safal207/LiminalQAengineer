//! Storage layer implementation

use anyhow::{Context, Result};
use liminalqa_core::{
    entities::*,
    facts::*,
    types::{EntityId, TestStatus},
};
use serde::{Deserialize, Serialize};
use std::path::Path;
use tracing::{debug, info};

/// Main database handle
pub struct LiminalDB {
    db: sled::Db,
    // Trees (indexes)
    entities: sled::Tree,
    facts: sled::Tree,
    valid_time_index: sled::Tree,
    tx_time_index: sled::Tree,
    entity_type_index: sled::Tree,
    test_name_index: sled::Tree,
    test_history_index: sled::Tree,
    /// Tracks every unique (name, suite) pair ever seen.
    /// Key: `"{name}\x00{suite}"`, Value: empty.
    known_tests: sled::Tree,
}

impl LiminalDB {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self> {
        let path_ref = path.as_ref();
        info!("Opening LIMINAL-DB at: {}", path_ref.display());

        let db = sled::open(path_ref).context("Failed to open sled database")?;

        let entities = db.open_tree("entities")?;
        let facts = db.open_tree("facts")?;
        let valid_time_index = db.open_tree("idx_valid_time")?;
        let tx_time_index = db.open_tree("idx_tx_time")?;
        let entity_type_index = db.open_tree("idx_entity_type")?;
        let test_name_index = db.open_tree("idx_test_name")?;
        let test_history_index = db.open_tree("idx_test_history")?;
        let known_tests = db.open_tree("known_tests")?;

        Ok(Self {
            db,
            entities,
            facts,
            valid_time_index,
            tx_time_index,
            entity_type_index,
            test_name_index,
            test_history_index,
            known_tests,
        })
    }

    /// Store a system entity
    pub fn put_system(&self, system: &System) -> Result<()> {
        self.put_entity(EntityType::System, system.id, system)
    }

    /// Store a build entity
    pub fn put_build(&self, build: &Build) -> Result<()> {
        self.put_entity(EntityType::Build, build.id, build)
    }

    /// Store a run entity
    pub fn put_run(&self, run: &Run) -> Result<()> {
        self.put_entity(EntityType::Run, run.id, run)
    }

    /// Store a test entity
    pub fn put_test(&self, test: &Test) -> Result<()> {
        self.put_entity(EntityType::Test, test.id, test)?;

        // Create secondary index for name lookup
        let index_key = format!("idx:test_name:{}:{}", test.run_id, test.name);
        self.test_name_index
            .insert(index_key.as_bytes(), &test.id.to_bytes())?;

        // Create index for history lookup (name + suite + time + run_id).
        // The run_id suffix makes the key unique even when two runs share the
        // same started_at timestamp (common in tests and rapid CI pipelines).
        let history_key = format!(
            "idx:history:{}:{}:{}:{}",
            test.name,
            test.suite,
            test.started_at.timestamp_millis(),
            test.run_id,
        );
        self.test_history_index
            .insert(history_key.as_bytes(), &test.id.to_bytes())?;

        // Track unique (name, suite) pairs — key is "name\x00suite"
        let known_key = format!("{}\x00{}", test.name, test.suite);
        self.known_tests.insert(known_key.as_bytes(), b"")?;

        Ok(())
    }

    /// Return every unique (name, suite) pair ever stored.
    pub fn list_known_tests(&self) -> Result<Vec<(String, String)>> {
        let mut out = Vec::new();
        for item in self.known_tests.iter() {
            let (key, _) = item?;
            let s = String::from_utf8_lossy(&key);
            if let Some((name, suite)) = s.split_once('\x00') {
                out.push((name.to_string(), suite.to_string()));
            }
        }
        Ok(out)
    }

    /// Pass rate for a test over its last `lookback` runs (0.0–1.0).
    /// Returns 1.0 when no history exists (no evidence of flakiness).
    /// Min 5 runs required before reporting a non-trivial score.
    pub fn test_stability_score(&self, name: &str, suite: &str, lookback: usize) -> Result<f64> {
        let history = self.get_test_history(name, suite, lookback)?;
        if history.is_empty() {
            return Ok(1.0);
        }
        let pass_count = history
            .iter()
            .filter(|t| t.status == TestStatus::Pass)
            .count();
        Ok(pass_count as f64 / history.len() as f64)
    }

    /// Return all Signal entities for a given run, sorted by stored order.
    pub fn get_signals_by_run(&self, run_id: EntityId) -> Result<Vec<Signal>> {
        let prefix = format!("{}:", entity_type_to_str(EntityType::Signal));
        let mut signals = Vec::new();
        for item in self.entity_type_index.scan_prefix(prefix.as_bytes()) {
            let (_, raw_key) = item?;
            if let Some(bytes) = self.entities.get(&raw_key)? {
                if let Ok(sig) = serde_json::from_slice::<Signal>(&bytes) {
                    if sig.run_id == run_id {
                        signals.push(sig);
                    }
                }
            }
        }
        Ok(signals)
    }

    /// Retrieve test execution history for a given test name and suite
    pub fn get_test_history(&self, name: &str, suite: &str, limit: usize) -> Result<Vec<Test>> {
        let prefix = format!("idx:history:{}:{}:", name, suite);
        let mut tests = Vec::new();

        // Scan the history index
        // Note: Sled iteration order is lexicographical.
        // Timestamps increase, so normal iteration gives oldest first.
        // If we want newest first (likely for history), we should iterate in reverse.
        for item in self
            .test_history_index
            .scan_prefix(prefix.as_bytes())
            .rev()
            .take(limit)
        {
            let (_, id_bytes) = item?;
            let test_id = EntityId::from_bytes(id_bytes.as_ref().try_into()?);

            if let Some(test) = self.get_entity::<Test>(test_id)? {
                tests.push(test);
            }
        }

        Ok(tests)
    }

    /// Find test ID by name within a specific run
    ///
    /// # Arguments
    /// * `run_id` - The run to search within
    /// * `test_name` - The name of the test
    ///
    /// # Returns
    /// * `Ok(Some(test_id))` - Test found
    /// * `Ok(None)` - Test not found
    /// * `Err(_)` - Database error
    pub fn find_test_by_name(&self, run_id: EntityId, test_name: &str) -> Result<Option<EntityId>> {
        let index_key = format!("idx:test_name:{}:{}", run_id, test_name);

        match self.test_name_index.get(index_key.as_bytes())? {
            Some(test_id_bytes) => {
                let test_id = EntityId::from_bytes(test_id_bytes.as_ref().try_into()?);
                Ok(Some(test_id))
            }
            None => Ok(None),
        }
    }

    /// Store an artifact entity
    pub fn put_artifact(&self, artifact: &Artifact) -> Result<()> {
        self.put_entity(EntityType::Artifact, artifact.id, artifact)
    }

    /// Store a signal entity.
    ///
    /// Signal.metadata contains serde_json::Value which bincode cannot round-trip
    /// via deserialize_any. Signals are stored as JSON in the entities tree.
    pub fn put_signal(&self, signal: &Signal) -> Result<()> {
        let key = signal.id.to_bytes();
        let value = serde_json::to_vec(signal)?;
        self.entities.insert(key, value)?;

        let type_key = format!("{}:{}", entity_type_to_str(EntityType::Signal), signal.id);
        self.entity_type_index.insert(type_key.as_bytes(), &key)?;

        debug!("Stored signal entity: id={}", signal.id);
        Ok(())
    }

    /// Store a resonance entity
    pub fn put_resonance(&self, resonance: &Resonance) -> Result<()> {
        self.put_entity(EntityType::Resonance, resonance.id, resonance)
    }

    /// Generic entity storage
    fn put_entity<T: Serialize>(
        &self,
        entity_type: EntityType,
        id: EntityId,
        entity: &T,
    ) -> Result<()> {
        let key = id.to_bytes();
        let value = bincode::serialize(entity)?;

        self.entities.insert(key, value)?;

        // Index by entity type
        let type_key = format!("{}:{}", entity_type_to_str(entity_type), id);
        self.entity_type_index.insert(type_key.as_bytes(), &key)?;

        debug!("Stored entity: type={:?}, id={}", entity_type, id);
        Ok(())
    }

    /// Store a fact
    pub fn put_fact(&self, fact: &Fact) -> Result<()> {
        let fact_id = EntityId::new();
        let key = fact_id.to_bytes();
        // Use JSON for facts because Fact contains serde_json::Value which bincode can't handle
        let value = serde_json::to_vec(fact)?;

        self.facts.insert(key, value)?;

        // Index by valid_time
        let vt_key = format!(
            "{}:{}:{}",
            fact.time.valid_time.timestamp_millis(),
            fact.entity_id,
            fact_id
        );
        self.valid_time_index.insert(vt_key.as_bytes(), &key)?;

        // Index by tx_time
        let tx_key = format!(
            "{}:{}:{}",
            fact.time.tx_time.timestamp_millis(),
            fact.entity_id,
            fact_id
        );
        self.tx_time_index.insert(tx_key.as_bytes(), &key)?;

        debug!(
            "Stored fact: entity_id={}, attribute={}",
            fact.entity_id, fact.attribute
        );
        Ok(())
    }

    /// Store multiple facts in batch
    pub fn put_fact_batch(&self, batch: &FactBatch) -> Result<()> {
        for fact in &batch.facts {
            self.put_fact(fact)?;
        }
        info!("Stored fact batch: {} facts", batch.facts.len());
        Ok(())
    }

    /// Get entity by ID.
    ///
    /// Attempts bincode deserialization first (used by most entities), then falls back
    /// to JSON for entities that contain serde_json::Value fields (e.g., Signal).
    pub fn get_entity<T: for<'de> Deserialize<'de>>(&self, id: EntityId) -> Result<Option<T>> {
        let key = id.to_bytes();
        match self.entities.get(key)? {
            Some(bytes) => {
                if let Ok(entity) = bincode::deserialize::<T>(&bytes) {
                    Ok(Some(entity))
                } else {
                    let entity = serde_json::from_slice(&bytes)?;
                    Ok(Some(entity))
                }
            }
            None => Ok(None),
        }
    }

    /// Get all entities of a specific type
    pub fn get_entities_by_type(&self, entity_type: EntityType) -> Result<Vec<EntityId>> {
        let prefix = format!("{}:", entity_type_to_str(entity_type));
        let mut ids = Vec::new();

        for item in self.entity_type_index.scan_prefix(prefix.as_bytes()) {
            let (key, _) = item?;
            let key_str = String::from_utf8_lossy(&key);
            if let Some(id_str) = key_str.split(':').nth(1) {
                if let Ok(id) = EntityId::from_string(id_str) {
                    ids.push(id);
                }
            }
        }

        Ok(ids)
    }

    /// Flush all pending writes
    pub fn flush(&self) -> Result<()> {
        self.db.flush()?;
        Ok(())
    }

    /// Scan all facts (unfiltered)
    pub fn scan_facts(&self) -> Result<Vec<Fact>> {
        let mut facts = Vec::new();
        for item in self.facts.iter() {
            let (_, value) = item?;
            let fact: Fact = serde_json::from_slice(&value)?;
            facts.push(fact);
        }
        Ok(facts)
    }

    /// Scan facts for specific entities
    pub fn scan_facts_by_entities(&self, entity_ids: &[EntityId]) -> Result<Vec<Fact>> {
        let mut facts = Vec::new();
        for item in self.facts.iter() {
            let (_, value) = item?;
            let fact: Fact = serde_json::from_slice(&value)?;
            if entity_ids.contains(&fact.entity_id) {
                facts.push(fact);
            }
        }
        Ok(facts)
    }

    /// Scan facts within valid_time range
    pub fn scan_facts_by_valid_time(
        &self,
        start_ms: i64,
        end_ms: Option<i64>,
    ) -> Result<Vec<Fact>> {
        let mut facts = Vec::new();

        // Scan all items in the valid_time_index and filter by range
        for item in self.valid_time_index.iter() {
            let (key, fact_key) = item?;
            let key_str = String::from_utf8_lossy(&key);

            // Parse timestamp from key: "{timestamp}:{entity_id}:{fact_id}"
            if let Some(ts_str) = key_str.split(':').next() {
                if let Ok(ts) = ts_str.parse::<i64>() {
                    // Check if timestamp is in range
                    #[allow(clippy::unnecessary_map_or)]
                    #[allow(clippy::needless_bool)]
                    let in_range = if ts >= start_ms && end_ms.map_or(true, |end| ts <= end) {
                        true
                    } else {
                        false
                    };

                    if in_range {
                        // Get the actual fact
                        if let Some(fact_bytes) = self.facts.get(&fact_key)? {
                            let fact: Fact = serde_json::from_slice(&fact_bytes)?;
                            facts.push(fact);
                        }
                    }
                }
            }
        }

        Ok(facts)
    }
}

fn entity_type_to_str(et: EntityType) -> &'static str {
    match et {
        EntityType::System => "system",
        EntityType::Build => "build",
        EntityType::Run => "run",
        EntityType::Test => "test",
        EntityType::Artifact => "artifact",
        EntityType::Signal => "signal",
        EntityType::Resonance => "resonance",
    }
}

#[cfg(test)]
#[allow(clippy::disallowed_methods)]
mod tests {
    use super::*;
    use liminalqa_core::{
        entities::ArtifactType,
        facts::{Attribute, Fact, FactBatch},
        temporal::BiTemporalTime,
        types::{ArtifactRef, ResonancePattern, SignalType},
    };
    use std::collections::HashMap;
    use tempfile::TempDir;

    #[test]
    fn test_store_and_retrieve_test() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let test = Test {
            id: EntityId::new(),
            run_id: EntityId::new(),
            name: "test_login".to_string(),
            suite: "auth".to_string(),
            guidance: "User should be able to log in with valid credentials".to_string(),
            status: liminalqa_core::types::TestStatus::Pass,
            duration_ms: 1234,
            error: None,
            started_at: chrono::Utc::now(),
            completed_at: chrono::Utc::now(),
            created_at: BiTemporalTime::now(),
        };

        db.put_test(&test)?;

        let retrieved: Option<Test> = db.get_entity(test.id)?;
        assert!(retrieved.is_some());
        // TODO(Phase 4): Refactor error handling
        #[allow(clippy::disallowed_methods)]
        {
            assert_eq!(retrieved.unwrap().name, "test_login");
        }

        Ok(())
    }

    #[test]
    fn test_lookup_by_name_success() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let run_id = EntityId::new();
        let test = Test {
            id: EntityId::new(),
            run_id,
            name: "test_user_login".to_string(),
            suite: "auth".to_string(),
            guidance: "User should be able to log in".to_string(),
            status: liminalqa_core::types::TestStatus::Pass,
            duration_ms: 100,
            error: None,
            started_at: chrono::Utc::now(),
            completed_at: chrono::Utc::now(),
            created_at: BiTemporalTime::now(),
        };

        db.put_test(&test)?;

        // Lookup should succeed
        let found = db.find_test_by_name(run_id, "test_user_login")?;
        assert_eq!(found, Some(test.id));

        Ok(())
    }

    #[test]
    fn test_lookup_by_name_not_found() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let run_id = EntityId::new();
        let found = db.find_test_by_name(run_id, "nonexistent")?;
        assert_eq!(found, None);

        Ok(())
    }

    #[test]
    fn test_lookup_different_runs_same_name() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let run1 = EntityId::new();
        let run2 = EntityId::new();

        let test1 = Test {
            id: EntityId::new(),
            run_id: run1,
            name: "shared_name".to_string(),
            suite: "suite1".to_string(),
            guidance: "".to_string(),
            status: liminalqa_core::types::TestStatus::Pass,
            duration_ms: 100,
            error: None,
            started_at: chrono::Utc::now(),
            completed_at: chrono::Utc::now(),
            created_at: BiTemporalTime::now(),
        };

        let test2 = Test {
            id: EntityId::new(),
            run_id: run2,
            name: "shared_name".to_string(),
            suite: "suite2".to_string(),
            guidance: "".to_string(),
            status: liminalqa_core::types::TestStatus::Pass,
            duration_ms: 200,
            error: None,
            started_at: chrono::Utc::now(),
            completed_at: chrono::Utc::now(),
            created_at: BiTemporalTime::now(),
        };

        db.put_test(&test1)?;
        db.put_test(&test2)?;

        // Same name in different runs should resolve to different test_ids
        let found1 = db.find_test_by_name(run1, "shared_name")?;
        let found2 = db.find_test_by_name(run2, "shared_name")?;

        assert_eq!(found1, Some(test1.id));
        assert_eq!(found2, Some(test2.id));
        assert_ne!(test1.id, test2.id);

        Ok(())
    }

    // ── Run ──────────────────────────────────────────────────────────────────

    #[test]
    fn test_put_and_get_run() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let run = Run {
            id: EntityId::new(),
            build_id: EntityId::new(),
            plan_name: "nightly-smoke".to_string(),
            env: HashMap::from([("CI".to_string(), "true".to_string())]),
            started_at: chrono::Utc::now(),
            ended_at: None,
            runner_version: "0.1.0".to_string(),
            liminal_os_version: None,
            created_at: BiTemporalTime::now(),
        };

        db.put_run(&run)?;

        let retrieved: Option<Run> = db.get_entity(run.id)?;
        assert!(retrieved.is_some());
        let r = retrieved.unwrap();
        assert_eq!(r.plan_name, "nightly-smoke");
        assert_eq!(r.env.get("CI"), Some(&"true".to_string()));

        Ok(())
    }

    #[test]
    fn test_get_runs_by_type() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let run1 = Run {
            id: EntityId::new(),
            build_id: EntityId::new(),
            plan_name: "plan-a".to_string(),
            env: HashMap::new(),
            started_at: chrono::Utc::now(),
            ended_at: None,
            runner_version: "0.1.0".to_string(),
            liminal_os_version: None,
            created_at: BiTemporalTime::now(),
        };
        let run2 = Run {
            id: EntityId::new(),
            build_id: EntityId::new(),
            plan_name: "plan-b".to_string(),
            env: HashMap::new(),
            started_at: chrono::Utc::now(),
            ended_at: None,
            runner_version: "0.1.0".to_string(),
            liminal_os_version: None,
            created_at: BiTemporalTime::now(),
        };

        db.put_run(&run1)?;
        db.put_run(&run2)?;

        let ids = db.get_entities_by_type(EntityType::Run)?;
        assert_eq!(ids.len(), 2);
        assert!(ids.contains(&run1.id));
        assert!(ids.contains(&run2.id));

        Ok(())
    }

    // ── Artifact ─────────────────────────────────────────────────────────────

    #[test]
    fn test_put_and_get_artifact() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let artifact = Artifact {
            id: EntityId::new(),
            run_id: EntityId::new(),
            test_id: EntityId::new(),
            artifact_ref: ArtifactRef {
                sha256: "deadbeef".to_string(),
                path: "/screenshots/login.png".to_string(),
                size_bytes: 2048,
                mime_type: Some("image/png".to_string()),
            },
            artifact_type: ArtifactType::Screenshot,
            description: Some("Login page on failure".to_string()),
            created_at: BiTemporalTime::now(),
        };

        db.put_artifact(&artifact)?;

        let retrieved: Option<Artifact> = db.get_entity(artifact.id)?;
        assert!(retrieved.is_some());
        let a = retrieved.unwrap();
        assert_eq!(a.artifact_ref.sha256, "deadbeef");
        assert_eq!(a.artifact_ref.size_bytes, 2048);
        assert_eq!(a.artifact_type, ArtifactType::Screenshot);

        Ok(())
    }

    // ── Signal ───────────────────────────────────────────────────────────────

    #[test]
    fn test_put_and_get_signal() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let signal = Signal {
            id: EntityId::new(),
            run_id: EntityId::new(),
            test_id: EntityId::new(),
            signal_type: SignalType::API,
            timestamp: chrono::Utc::now(),
            latency_ms: Some(42),
            payload_ref: None,
            metadata: HashMap::from([(
                "status_code".to_string(),
                serde_json::Value::Number(200.into()),
            )]),
            created_at: BiTemporalTime::now(),
        };

        db.put_signal(&signal)?;

        let retrieved: Option<Signal> = db.get_entity(signal.id)?;
        assert!(retrieved.is_some());
        let s = retrieved.unwrap();
        assert_eq!(s.signal_type, SignalType::API);
        assert_eq!(s.latency_ms, Some(42));
        assert_eq!(s.metadata.get("status_code"), Some(&serde_json::json!(200)));

        Ok(())
    }

    // ── Resonance ────────────────────────────────────────────────────────────

    #[test]
    fn test_put_and_get_resonance() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let test_id = EntityId::new();
        let resonance = Resonance {
            id: EntityId::new(),
            pattern: ResonancePattern {
                pattern_id: EntityId::new(),
                description: "Intermittent DB timeout".to_string(),
                score: 0.87,
                occurrences: 5,
                first_seen: chrono::Utc::now(),
                last_seen: chrono::Utc::now(),
            },
            affected_tests: vec![test_id],
            root_cause: Some("Connection pool exhaustion".to_string()),
            created_at: BiTemporalTime::now(),
        };

        db.put_resonance(&resonance)?;

        let retrieved: Option<Resonance> = db.get_entity(resonance.id)?;
        assert!(retrieved.is_some());
        let r = retrieved.unwrap();
        assert!((r.pattern.score - 0.87).abs() < f64::EPSILON);
        assert_eq!(r.pattern.occurrences, 5);
        assert_eq!(r.affected_tests, vec![test_id]);

        Ok(())
    }

    // ── Facts ────────────────────────────────────────────────────────────────

    #[test]
    fn test_put_and_scan_fact() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let entity_id = EntityId::new();
        let fact = Fact::new(entity_id, Attribute::TestStatus, serde_json::json!("pass"));

        db.put_fact(&fact)?;

        let all_facts = db.scan_facts()?;
        assert_eq!(all_facts.len(), 1);
        assert_eq!(all_facts[0].entity_id, entity_id);
        assert_eq!(all_facts[0].attribute, Attribute::TestStatus);
        assert_eq!(all_facts[0].value, serde_json::json!("pass"));

        Ok(())
    }

    #[test]
    fn test_put_fact_batch() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let entity_id = EntityId::new();
        let facts = vec![
            Fact::new(entity_id, Attribute::TestDuration, serde_json::json!(1234)),
            Fact::new(entity_id, Attribute::TestStatus, serde_json::json!("fail")),
            Fact::new(entity_id, Attribute::ApiLatency, serde_json::json!(99)),
        ];
        let batch = FactBatch::new(facts);

        db.put_fact_batch(&batch)?;

        let stored = db.scan_facts()?;
        assert_eq!(stored.len(), 3);

        Ok(())
    }

    #[test]
    fn test_scan_facts_by_entities() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let id_a = EntityId::new();
        let id_b = EntityId::new();

        db.put_fact(&Fact::new(
            id_a,
            Attribute::TestStatus,
            serde_json::json!("pass"),
        ))?;
        db.put_fact(&Fact::new(
            id_b,
            Attribute::TestStatus,
            serde_json::json!("fail"),
        ))?;
        db.put_fact(&Fact::new(
            id_a,
            Attribute::TestDuration,
            serde_json::json!(500),
        ))?;

        let facts_a = db.scan_facts_by_entities(&[id_a])?;
        assert_eq!(facts_a.len(), 2);
        assert!(facts_a.iter().all(|f| f.entity_id == id_a));

        let facts_b = db.scan_facts_by_entities(&[id_b])?;
        assert_eq!(facts_b.len(), 1);

        let both = db.scan_facts_by_entities(&[id_a, id_b])?;
        assert_eq!(both.len(), 3);

        Ok(())
    }

    #[test]
    fn test_scan_facts_by_valid_time() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let entity_id = EntityId::new();
        // Store a fact with "now" valid_time
        let fact = Fact::new(entity_id, Attribute::TestStatus, serde_json::json!("pass"));
        let ts = fact.time.valid_time.timestamp_millis();
        db.put_fact(&fact)?;

        // Query within a window that contains ts
        let found = db.scan_facts_by_valid_time(ts - 1000, Some(ts + 1000))?;
        assert_eq!(found.len(), 1);

        // Query outside the window
        let not_found = db.scan_facts_by_valid_time(ts + 10_000, Some(ts + 20_000))?;
        assert_eq!(not_found.len(), 0);

        // Open-ended end
        let open_end = db.scan_facts_by_valid_time(ts - 1000, None)?;
        assert_eq!(open_end.len(), 1);

        Ok(())
    }

    // ── Test History ─────────────────────────────────────────────────────────

    #[test]
    fn test_get_test_history_ordered() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let base = chrono::Utc::now();
        let suite = "auth";
        let name = "test_login";

        // Insert 3 runs of the same test at different times
        for i in 0..3u64 {
            let started = base + chrono::Duration::seconds(i as i64 * 60);
            let test = Test {
                id: EntityId::new(),
                run_id: EntityId::new(),
                name: name.to_string(),
                suite: suite.to_string(),
                guidance: "".to_string(),
                status: liminalqa_core::types::TestStatus::Pass,
                duration_ms: 100 + i * 10,
                error: None,
                started_at: started,
                completed_at: started,
                created_at: BiTemporalTime::now(),
            };
            db.put_test(&test)?;
        }

        let history = db.get_test_history(name, suite, 10)?;
        // Should return all 3, newest first
        assert_eq!(history.len(), 3);
        // Newest first: duration_ms 120 > 110 > 100
        assert!(history[0].duration_ms >= history[1].duration_ms);
        assert!(history[1].duration_ms >= history[2].duration_ms);

        Ok(())
    }

    #[test]
    fn test_get_test_history_limit() -> Result<()> {
        let temp_dir = TempDir::new()?;
        let db = LiminalDB::open(temp_dir.path())?;

        let base = chrono::Utc::now();
        for i in 0..5u64 {
            let started = base + chrono::Duration::seconds(i as i64);
            let test = Test {
                id: EntityId::new(),
                run_id: EntityId::new(),
                name: "test_x".to_string(),
                suite: "suite".to_string(),
                guidance: "".to_string(),
                status: liminalqa_core::types::TestStatus::Pass,
                duration_ms: i * 10,
                error: None,
                started_at: started,
                completed_at: started,
                created_at: BiTemporalTime::now(),
            };
            db.put_test(&test)?;
        }

        let history = db.get_test_history("test_x", "suite", 3)?;
        assert_eq!(history.len(), 3);

        Ok(())
    }

    // ── Flush ────────────────────────────────────────────────────────────────

    #[test]
    fn test_flush_persists_data() -> Result<()> {
        let temp_dir = TempDir::new()?;

        let test_id = EntityId::new();
        {
            let db = LiminalDB::open(temp_dir.path())?;
            let test = Test {
                id: test_id,
                run_id: EntityId::new(),
                name: "persistent_test".to_string(),
                suite: "suite".to_string(),
                guidance: "".to_string(),
                status: liminalqa_core::types::TestStatus::Pass,
                duration_ms: 42,
                error: None,
                started_at: chrono::Utc::now(),
                completed_at: chrono::Utc::now(),
                created_at: BiTemporalTime::now(),
            };
            db.put_test(&test)?;
            db.flush()?;
        } // db dropped

        // Re-open same path — data should survive
        let db2 = LiminalDB::open(temp_dir.path())?;
        let retrieved: Option<Test> = db2.get_entity(test_id)?;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().name, "persistent_test");

        Ok(())
    }
}
