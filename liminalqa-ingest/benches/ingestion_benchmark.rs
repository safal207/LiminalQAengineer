//! Benchmarks for LiminalQA ingestion performance

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use liminalqa_core::{entities::*, temporal::BiTemporalTime, types::*};
use liminalqa_db::LiminalDB;
use std::hint::black_box;

#[allow(clippy::unwrap_used)]
fn bench_single_test_ingestion(c: &mut Criterion) {
    c.bench_function("ingest_single_test", |b| {
        let temp = tempfile::tempdir().unwrap();
        let db = LiminalDB::open(temp.path()).unwrap();

        b.iter(|| {
            let test = Test {
                id: EntityId::new(),
                run_id: EntityId::new(),
                name: "benchmark_test".to_string(),
                suite: "benchmark".to_string(),
                guidance: String::new(),
                status: TestStatus::Pass,
                duration_ms: 100,
                error: None,
                started_at: chrono::Utc::now(),
                completed_at: chrono::Utc::now(),
                created_at: BiTemporalTime::now(),
            };

            db.put_test(&test).unwrap();
            black_box(());
        });
    });
}

#[allow(clippy::unwrap_used)]
fn bench_batch_test_ingestion(c: &mut Criterion) {
    let mut group = c.benchmark_group("batch_ingestion");

    for size in [10, 100, 1000].iter() {
        group.bench_with_input(BenchmarkId::from_parameter(size), size, |b, &size| {
            let temp = tempfile::tempdir().unwrap();
            let db = LiminalDB::open(temp.path()).unwrap();
            let run_id = EntityId::new();

            b.iter(|| {
                for i in 0..size {
                    let test = Test {
                        id: EntityId::new(),
                        run_id,
                        name: format!("test_{}", i),
                        suite: "benchmark".to_string(),
                        guidance: String::new(),
                        status: TestStatus::Pass,
                        duration_ms: 100,
                        error: None,
                        started_at: chrono::Utc::now(),
                        completed_at: chrono::Utc::now(),
                        created_at: BiTemporalTime::now(),
                    };

                    db.put_test(&test).unwrap();
                    black_box(());
                }
                db.flush().unwrap();
            });
        });
    }

    group.finish();
}

#[allow(clippy::unwrap_used)]
fn bench_test_lookup(c: &mut Criterion) {
    let temp = tempfile::tempdir().unwrap();
    let db = LiminalDB::open(temp.path()).unwrap();
    let run_id = EntityId::new();

    // Prepare 1000 tests
    for i in 0..1000 {
        let test = Test {
            id: EntityId::new(),
            run_id,
            name: format!("test_{}", i),
            suite: "benchmark".to_string(),
            guidance: String::new(),
            status: TestStatus::Pass,
            duration_ms: 100,
            error: None,
            started_at: chrono::Utc::now(),
            completed_at: chrono::Utc::now(),
            created_at: BiTemporalTime::now(),
        };
        db.put_test(&test).unwrap();
    }

    c.bench_function("lookup_test_by_name", |b| {
        b.iter(|| {
            db.find_test_by_name(run_id, "test_500").unwrap();
            black_box(());
        });
    });
}

criterion_group!(
    benches,
    bench_single_test_ingestion,
    bench_batch_test_ingestion,
    bench_test_lookup
);
criterion_main!(benches);
