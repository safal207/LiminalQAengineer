//! Storage layer implementation

use anyhow::{Context, Result};
use liminalqa_core::{
    entities::*, facts::*, temporal::BiTemporalTime, types::EntityId,
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
}

impl LiminalDB {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self> {
        let path_ref = path.as_ref();
        info!("Opening LIMINAL-DB at: {}", path_ref.display());

        let db = sled::open(path_ref)
            .context("Failed to open sled database")?;

        let entities = db.open_tree("entities")?;
        let facts = db.open_tree("facts")?;
        let valid_time_index = db.open_tree("idx_valid_time")?;
        let tx_time_index = db.open_tree("idx_tx_time")?;
        let entity_type_index = db.open_tree("idx_entity_type")?;

        Ok(Self {
            db,
            entities,
            facts,
            valid_time_index,
            tx_time_index,
            entity_type_index,
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
        self.put_entity(EntityType::Test, test.id, test)
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

        self.entities.insert(&key, value)?;

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
        let value = bincode::serialize(fact)?;

        self.facts.insert(&key, value)?;

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

        debug!("Stored fact: entity_id={}, attribute={}", fact.entity_id, fact.attribute);
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
        match self.entities.get(&key)? {
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
        assert_eq!(retrieved.unwrap().name, "test_login");

        Ok(())
    }
}
