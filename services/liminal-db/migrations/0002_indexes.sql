-- LIMINAL-DB Indexes for bi-temporal queries and analytics

-- Test fact indexes
create index test_fact_name_idx on test_fact (test_name);
create index test_fact_status_idx on test_fact (status);
create index test_fact_run_idx on test_fact (run_id);
create index test_fact_suite_idx on test_fact (suite);

-- Bi-temporal range index (GiST for overlaps)
create index test_fact_valid_range_idx on test_fact using gist (tsrange(valid_from, valid_to, '[)'));

-- Transaction time index (for "as-of" queries)
create index test_fact_tx_at_idx on test_fact (tx_at);

-- Composite index for common queries
create index test_fact_run_name_valid_idx on test_fact (run_id, test_name, valid_from);

-- Signal indexes
create index signal_run_idx on signal (run_id);
create index signal_kind_idx on signal (kind);
create index signal_at_idx on signal (at);
create index signal_kind_at_idx on signal (kind, at);
create index signal_test_name_idx on signal (test_name) where test_name is not null;

-- Run indexes
create index run_started_at_idx on run (started_at);
create index run_build_idx on run (build_id);

-- Artifact indexes
create index artifact_run_idx on artifact (run_id);
create index artifact_kind_idx on artifact (kind);
create index artifact_sha_idx on artifact (path_sha256);

-- Resonance indexes
create index resonance_pattern_idx on resonance (pattern_id);
create index resonance_score_idx on resonance (score);
create index resonance_first_seen_idx on resonance (first_seen);

-- Full-text search on test names (for fuzzy matching)
create index test_fact_name_trgm_idx on test_fact using gin (test_name gin_trgm_ops);
create extension if not exists pg_trgm;
