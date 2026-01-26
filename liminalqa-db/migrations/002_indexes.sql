-- 002_indexes.sql

-- Runs
CREATE INDEX idx_runs_started_at ON runs(started_at DESC);
CREATE INDEX idx_runs_plan_name ON runs(plan_name);

-- Tests
CREATE INDEX idx_tests_run_id ON tests(run_id);
CREATE INDEX idx_tests_name_suite ON tests(name, suite);
CREATE INDEX idx_tests_executed_at ON tests(executed_at DESC);
CREATE INDEX idx_tests_status ON tests(status);

-- Phase 5 optimization
CREATE INDEX idx_tests_protocol_resonance ON tests(self_resonance_score) WHERE self_resonance_score IS NOT NULL;
