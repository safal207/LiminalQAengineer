//! Criterion benchmarks for LIMINAL-DB storage layer.
//!
//! Run with:
//!   cargo bench -p liminalqa-db
//!
//! HTML report lands in target/criterion/

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use liminalqa_core::{
    entities::{Artifact, ArtifactType, Run, Signal, Test},
    facts::{Attribute, Fact, FactBatch},
    temporal::BiTemporalTime,
    types::{ArtifactRef, EntityId, SignalType, TestStatus},
};
use liminalqa_db::LiminalDB;
use std::collections::HashMap;
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

fn open_db() -> (LiminalDB, TempDir) {
    let dir = TempDir::new().unwrap();
    let db = LiminalDB::open(dir.path()).unwrap();
    (db, dir)
}

fn make_run() -> Run {
    Run {
        id: EntityId::new(),
        build_id: EntityId::new(),
        plan_name: "bench-plan".to_string(),
        env: HashMap::from([("CI".to_string(), "true".to_string())]),
        started_at: chrono::Utc::now(),
        ended_at: None,
        runner_version: "0.1.0".to_string(),
        liminal_os_version: None,
        created_at: BiTemporalTime::now(),
    }
}

fn make_test(run_id: EntityId, name: &str) -> Test {
    Test {
        id: EntityId::new(),
        run_id,
        name: name.to_string(),
        suite: "bench".to_string(),
        guidance: "Benchmark test".to_string(),
        status: TestStatus::Pass,
        duration_ms: 42,
        error: None,
        started_at: chrono::Utc::now(),
        completed_at: chrono::Utc::now(),
        created_at: BiTemporalTime::now(),
    }
}

fn make_signal(run_id: EntityId, test_id: EntityId) -> Signal {
    Signal {
        id: EntityId::new(),
        run_id,
        test_id,
        signal_type: SignalType::API,
        timestamp: chrono::Utc::now(),
        latency_ms: Some(10),
        payload_ref: None,
        metadata: HashMap::from([("status".to_string(), serde_json::json!(200))]),
        created_at: BiTemporalTime::now(),
    }
}

fn make_artifact(run_id: EntityId, test_id: EntityId) -> Artifact {
    Artifact {
        id: EntityId::new(),
        run_id,
        test_id,
        artifact_ref: ArtifactRef {
            sha256: "a".repeat(64),
            path: "/bench/screenshot.png".to_string(),
            size_bytes: 4096,
            mime_type: Some("image/png".to_string()),
        },
        artifact_type: ArtifactType::Screenshot,
        description: None,
        created_at: BiTemporalTime::now(),
    }
}

fn make_fact(entity_id: EntityId) -> Fact {
    Fact::new(entity_id, Attribute::TestStatus, serde_json::json!("pass"))
}

// ---------------------------------------------------------------------------
// Benchmarks: individual write operations
// ---------------------------------------------------------------------------

fn bench_put_run(c: &mut Criterion) {
    let (db, _dir) = open_db();
    c.bench_function("put_run", |b| {
        b.iter(|| {
            db.put_run(&make_run()).unwrap();
        });
    });
}

fn bench_put_test(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let run_id = EntityId::new();
    let mut counter = 0u64;

    c.bench_function("put_test", |b| {
        b.iter(|| {
            counter += 1;
            db.put_test(&make_test(run_id, &format!("test_{}", counter)))
                .unwrap();
        });
    });
}

fn bench_put_signal(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let run_id = EntityId::new();
    let test_id = EntityId::new();

    c.bench_function("put_signal", |b| {
        b.iter(|| {
            db.put_signal(&make_signal(run_id, test_id)).unwrap();
        });
    });
}

fn bench_put_artifact(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let run_id = EntityId::new();
    let test_id = EntityId::new();

    c.bench_function("put_artifact", |b| {
        b.iter(|| {
            db.put_artifact(&make_artifact(run_id, test_id)).unwrap();
        });
    });
}

fn bench_put_fact(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let entity_id = EntityId::new();

    c.bench_function("put_fact", |b| {
        b.iter(|| {
            db.put_fact(&make_fact(entity_id)).unwrap();
        });
    });
}

// ---------------------------------------------------------------------------
// Benchmarks: batch operations
// ---------------------------------------------------------------------------

fn bench_put_fact_batch(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let entity_id = EntityId::new();

    let mut group = c.benchmark_group("put_fact_batch");

    for size in [10usize, 100, 1_000] {
        group.throughput(Throughput::Elements(size as u64));
        group.bench_with_input(BenchmarkId::from_parameter(size), &size, |b, &n| {
            b.iter(|| {
                let facts: Vec<Fact> = (0..n).map(|_| make_fact(entity_id)).collect();
                db.put_fact_batch(&FactBatch::new(facts)).unwrap();
            });
        });
    }
    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmarks: read operations
// ---------------------------------------------------------------------------

fn bench_get_entity(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let run_id = EntityId::new();
    let test = make_test(run_id, "bench_test");
    let id = test.id;
    db.put_test(&test).unwrap();

    c.bench_function("get_entity_test", |b| {
        b.iter(|| {
            db.get_entity::<Test>(id).unwrap().unwrap();
        });
    });
}

fn bench_find_test_by_name(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let run_id = EntityId::new();
    db.put_test(&make_test(run_id, "target_test")).unwrap();

    c.bench_function("find_test_by_name", |b| {
        b.iter(|| {
            db.find_test_by_name(run_id, "target_test")
                .unwrap()
                .unwrap();
        });
    });
}

fn bench_get_test_history(c: &mut Criterion) {
    let (db, _dir) = open_db();
    // Pre-populate 20 historical runs of the same test
    let base = chrono::Utc::now();
    for i in 0u64..20 {
        let started = base + chrono::Duration::seconds(i as i64 * 60);
        let mut t = make_test(EntityId::new(), "history_test");
        t.run_id = EntityId::new();
        t.suite = "history_suite".to_string();
        t.started_at = started;
        t.completed_at = started;
        db.put_test(&t).unwrap();
    }

    c.bench_function("get_test_history_20", |b| {
        b.iter(|| {
            db.get_test_history("history_test", "history_suite", 20)
                .unwrap();
        });
    });
}

fn bench_get_entities_by_type(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let run_id = EntityId::new();

    // Pre-populate 100 tests
    for i in 0..100 {
        db.put_test(&make_test(run_id, &format!("t{}", i))).unwrap();
    }

    c.bench_function("get_entities_by_type_100tests", |b| {
        b.iter(|| {
            db.get_entities_by_type(liminalqa_core::entities::EntityType::Test)
                .unwrap();
        });
    });
}

fn bench_scan_facts(c: &mut Criterion) {
    let (db, _dir) = open_db();
    let id = EntityId::new();

    // Pre-populate 500 facts
    let facts: Vec<Fact> = (0..500).map(|_| make_fact(id)).collect();
    db.put_fact_batch(&FactBatch::new(facts)).unwrap();

    c.bench_function("scan_facts_500", |b| {
        b.iter(|| {
            db.scan_facts().unwrap();
        });
    });
}

// ---------------------------------------------------------------------------
// Benchmarks: full ingest pipeline (simulates one test run)
// ---------------------------------------------------------------------------

fn bench_full_ingest_pipeline(c: &mut Criterion) {
    let mut group = c.benchmark_group("full_ingest_pipeline");

    // Simulate ingesting N tests + N signals + N artifacts per run
    for n in [10usize, 50, 100] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &count| {
            b.iter(|| {
                let (db, _dir) = open_db();
                let run = make_run();
                let run_id = run.id;
                db.put_run(&run).unwrap();

                for i in 0..count {
                    let test = make_test(run_id, &format!("test_{}", i));
                    let test_id = test.id;
                    db.put_test(&test).unwrap();
                    db.put_signal(&make_signal(run_id, test_id)).unwrap();
                    db.put_artifact(&make_artifact(run_id, test_id)).unwrap();
                }
            });
        });
    }
    group.finish();
}

// ---------------------------------------------------------------------------
// Criterion groups
// ---------------------------------------------------------------------------

criterion_group!(
    writes,
    bench_put_run,
    bench_put_test,
    bench_put_signal,
    bench_put_artifact,
    bench_put_fact,
    bench_put_fact_batch,
);

criterion_group!(
    reads,
    bench_get_entity,
    bench_find_test_by_name,
    bench_get_test_history,
    bench_get_entities_by_type,
    bench_scan_facts,
);

criterion_group!(pipeline, bench_full_ingest_pipeline);

criterion_main!(writes, reads, pipeline);
