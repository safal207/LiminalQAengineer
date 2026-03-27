//! Property-based tests for liminalqa-db storage and query layers.
//!
//! Run with: cargo test -p liminalqa-db

use chrono::{TimeZone, Utc};
use liminalqa_core::{
    facts::{Attribute, Fact, FactBatch},
    temporal::BiTemporalTime,
    types::EntityId,
};
use liminalqa_db::{LiminalDB, Query};
use proptest::prelude::*;
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn open_db() -> (LiminalDB, TempDir) {
    let dir = TempDir::new().unwrap();
    let db = LiminalDB::open(dir.path()).unwrap();
    (db, dir)
}

/// Cycle through a fixed set of attributes to avoid monotone keys.
fn attr_for(i: usize) -> Attribute {
    match i % 6 {
        0 => Attribute::TestStatus,
        1 => Attribute::TestDuration,
        2 => Attribute::TestError,
        3 => Attribute::ApiLatency,
        4 => Attribute::RunStatus,
        _ => Attribute::ResonanceScore,
    }
}

fn make_fact(entity_id: EntityId, i: usize) -> Fact {
    Fact::new(entity_id, attr_for(i), serde_json::json!(i as i64))
}

fn make_fact_at_ms(entity_id: EntityId, valid_ms: i64) -> Fact {
    let valid_time = Utc.timestamp_millis_opt(valid_ms).unwrap();
    Fact::with_time(
        entity_id,
        Attribute::TestStatus,
        serde_json::json!("pass"),
        BiTemporalTime::with_times(valid_time, valid_time),
    )
}

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------

fn arb_entity_id() -> impl Strategy<Value = EntityId> {
    any::<u128>().prop_map(EntityId::from)
}

// ---------------------------------------------------------------------------
// Properties: Fact upsert correctness
// ---------------------------------------------------------------------------

proptest! {
    /// After inserting N facts, scan_facts() returns exactly N facts.
    #[test]
    fn prop_fact_count_after_n_inserts(n in 0usize..40) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n {
            db.put_fact(&make_fact(entity_id, i)).unwrap();
        }

        let stored = db.scan_facts().unwrap();
        prop_assert_eq!(stored.len(), n);
    }

    /// FactBatch::put stores every fact in the batch — scan returns the same count.
    #[test]
    fn prop_factbatch_count_preserved(n in 0usize..40) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        let facts: Vec<Fact> = (0..n).map(|i| make_fact(entity_id, i)).collect();
        let batch = FactBatch::new(facts);
        db.put_fact_batch(&batch).unwrap();

        let stored = db.scan_facts().unwrap();
        prop_assert_eq!(stored.len(), n);
    }

    /// Inserting more facts never decreases the total count (monotone growth).
    #[test]
    fn prop_fact_count_monotone(
        n_first in 1usize..20,
        n_second in 1usize..20,
    ) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n_first {
            db.put_fact(&make_fact(entity_id, i)).unwrap();
        }
        let count_before = db.scan_facts().unwrap().len();

        for i in 0..n_second {
            db.put_fact(&make_fact(entity_id, n_first + i)).unwrap();
        }
        let count_after = db.scan_facts().unwrap().len();

        prop_assert!(count_after >= count_before);
        prop_assert_eq!(count_after, count_before + n_second);
    }
}

// ---------------------------------------------------------------------------
// Properties: Entity filter correctness
// ---------------------------------------------------------------------------

proptest! {
    /// scan_facts_by_entities([id]) returns only facts for that entity.
    #[test]
    fn prop_entity_filter_only_matching(
        n_target in 1usize..20,
        n_other in 1usize..20,
    ) {
        let (db, _dir) = open_db();
        let target = EntityId::new();
        let other = EntityId::new();

        for i in 0..n_target {
            db.put_fact(&make_fact(target, i)).unwrap();
        }
        for i in 0..n_other {
            db.put_fact(&make_fact(other, i)).unwrap();
        }

        let facts = db.scan_facts_by_entities(&[target]).unwrap();
        prop_assert_eq!(facts.len(), n_target);
        prop_assert!(facts.iter().all(|f| f.entity_id == target));
    }

    /// scan_facts_by_entities result is always a subset of scan_facts.
    #[test]
    fn prop_entity_filter_subset_of_all(
        n in 1usize..20,
        target in arb_entity_id(),
    ) {
        let (db, _dir) = open_db();
        let other = EntityId::new();

        for i in 0..n {
            db.put_fact(&make_fact(target, i)).unwrap();
            db.put_fact(&make_fact(other, i)).unwrap();
        }

        let all = db.scan_facts().unwrap();
        let filtered = db.scan_facts_by_entities(&[target]).unwrap();

        prop_assert!(filtered.len() <= all.len());
        prop_assert!(filtered.iter().all(|f| f.entity_id == target));
    }

    /// Querying for two entities returns facts for both, no more.
    #[test]
    fn prop_two_entity_filter_union(
        n_a in 1usize..15,
        n_b in 1usize..15,
    ) {
        let (db, _dir) = open_db();
        let id_a = EntityId::new();
        let id_b = EntityId::new();
        let id_c = EntityId::new();

        for i in 0..n_a { db.put_fact(&make_fact(id_a, i)).unwrap(); }
        for i in 0..n_b { db.put_fact(&make_fact(id_b, i)).unwrap(); }
        // Noise: facts for a third entity
        for i in 0..5    { db.put_fact(&make_fact(id_c, i)).unwrap(); }

        let union = db.scan_facts_by_entities(&[id_a, id_b]).unwrap();
        prop_assert_eq!(union.len(), n_a + n_b);
        prop_assert!(union.iter().all(|f| f.entity_id == id_a || f.entity_id == id_b));
    }
}

// ---------------------------------------------------------------------------
// Properties: Valid time range filter
// ---------------------------------------------------------------------------

proptest! {
    /// Every fact returned by scan_facts_by_valid_time has valid_time in [start, end].
    #[test]
    fn prop_valid_time_filter_containment(
        base_ms in 1_000_000_000_000i64..1_800_000_000_000i64,
        window_ms in 10_000i64..1_000_000i64,
        n_inside in 1usize..8,
        n_outside in 1usize..8,
    ) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();
        let start_ms = base_ms;
        let end_ms = base_ms + window_ms;
        let step = window_ms / (n_inside as i64 + 1);

        // Facts strictly inside [start, end]
        for i in 0..n_inside {
            let ts = start_ms + step * (i as i64 + 1);
            db.put_fact(&make_fact_at_ms(entity_id, ts)).unwrap();
        }
        // Facts strictly outside (after end)
        for i in 0..n_outside {
            let ts = end_ms + 1 + i as i64 * 1_000;
            db.put_fact(&make_fact_at_ms(entity_id, ts)).unwrap();
        }

        let found = db.scan_facts_by_valid_time(start_ms, Some(end_ms)).unwrap();

        for fact in &found {
            let ts = fact.time.valid_time.timestamp_millis();
            prop_assert!(
                ts >= start_ms && ts <= end_ms,
                "fact ts {} not in [{}, {}]",
                ts, start_ms, end_ms
            );
        }
        prop_assert_eq!(found.len(), n_inside);
    }

    /// Open-ended scan returns >= facts compared to a closed window ending at the same point.
    #[test]
    fn prop_open_valid_time_superset_of_closed(
        base_ms in 1_000_000_000_000i64..1_800_000_000_000i64,
        n in 1usize..10,
    ) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n {
            db.put_fact(&make_fact_at_ms(entity_id, base_ms + i as i64 * 1_000)).unwrap();
        }

        let end_ms = base_ms + n as i64 * 1_000;
        let closed = db.scan_facts_by_valid_time(base_ms, Some(end_ms)).unwrap();
        let open   = db.scan_facts_by_valid_time(base_ms, None).unwrap();

        prop_assert!(open.len() >= closed.len());
    }
}

// ---------------------------------------------------------------------------
// Properties: Query limit
// ---------------------------------------------------------------------------

proptest! {
    /// A query with limit L returns at most L facts, regardless of total stored.
    #[test]
    fn prop_query_limit_upper_bound(
        n_facts in 1usize..30,
        limit in 1usize..25,
    ) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n_facts {
            db.put_fact(&make_fact(entity_id, i)).unwrap();
        }

        let result = Query::new().limit(limit).execute(&db).unwrap();
        prop_assert!(result.facts.len() <= limit);
        prop_assert_eq!(result.facts.len(), result.total);
    }

    /// A query without limit returns every stored fact (total and len agree).
    #[test]
    fn prop_query_no_limit_returns_all(n_facts in 0usize..30) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n_facts {
            db.put_fact(&make_fact(entity_id, i)).unwrap();
        }

        let result = Query::new().execute(&db).unwrap();
        prop_assert_eq!(result.total, n_facts);
        prop_assert_eq!(result.facts.len(), result.total);
    }

    /// Adding a limit never returns MORE facts than without a limit.
    #[test]
    fn prop_limited_query_le_unlimited(
        n_facts in 1usize..30,
        limit in 1usize..25,
    ) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n_facts {
            db.put_fact(&make_fact(entity_id, i)).unwrap();
        }

        let unlimited = Query::new().execute(&db).unwrap().total;
        let limited   = Query::new().limit(limit).execute(&db).unwrap().total;

        prop_assert!(limited <= unlimited);
    }
}

// ---------------------------------------------------------------------------
// Properties: Query total == facts.len() invariant
// ---------------------------------------------------------------------------

proptest! {
    /// QueryResult.total always equals QueryResult.facts.len().
    #[test]
    fn prop_query_result_total_consistent(n_facts in 0usize..20) {
        let (db, _dir) = open_db();
        let entity_id = EntityId::new();

        for i in 0..n_facts {
            db.put_fact(&make_fact(entity_id, i)).unwrap();
        }

        let result = Query::new().execute(&db).unwrap();
        prop_assert_eq!(result.total, result.facts.len());
    }
}
