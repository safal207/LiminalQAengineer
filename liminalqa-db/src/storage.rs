//! Storage layer implementation

use anyhow::{Context, Result};
use liminalqa_core::{entities::*, facts::*, types::EntityId};
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

        Ok(Self {
            db,
            entities,
            facts,
            valid_time_index,
            tx_time_index,
            entity_type_index,
            test_name_index,
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

        Ok(())
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

    /// Store a signal entity
    pub fn put_signal(&self, signal: &Signal) -> Result<()> {
        self.put_entity(EntityType::Signal, signal.id, signal)
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

    /// Get entity by ID
    pub fn get_entity<T: for<'de> Deserialize<'de>>(&self, id: EntityId) -> Result<Option<T>> {
        let key = id.to_bytes();
        match self.entities.get(key)? {
            Some(bytes) => {
                let entity = bincode::deserialize(&bytes)?;
                Ok(Some(entity))
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
                    if ts >= start_ms && end_ms.map_or(true, |end| ts <= end) {
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
mod tests {
    use super::*;
    use liminalqa_core::temporal::BiTemporalTime;
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
        if let Some(t) = retrieved {
            assert_eq!(t.name, "test_login");
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
}
