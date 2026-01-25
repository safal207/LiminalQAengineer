-- runs table
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    build_id TEXT,
    plan_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'passed', 'failed', 'error')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    environment JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_runs_started_at ON runs(started_at DESC);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_plan_name ON runs(plan_name);

-- Tests table
CREATE TABLE tests (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    suite TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'skipped', 'error', 'xfail', 'flake', 'timeout')),
    duration_ms INTEGER NOT NULL,
    error_message TEXT,
    stack_trace TEXT,
    metadata JSONB,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tests_run_id ON tests(run_id);
CREATE INDEX idx_tests_name_suite ON tests(name, suite);
CREATE INDEX idx_tests_executed_at ON tests(executed_at DESC);
CREATE INDEX idx_tests_status ON tests(status);

-- Baselines table (for drift detection)
CREATE TABLE baselines (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    suite TEXT NOT NULL,
    mean_duration_ms DOUBLE PRECISION NOT NULL,
    stddev_duration_ms DOUBLE PRECISION NOT NULL,
    sample_size INTEGER NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(test_name, suite)
);

CREATE INDEX idx_baselines_test_suite ON baselines(test_name, suite);

-- Resonance scores table
CREATE TABLE resonance_scores (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    suite TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
    correlated_tests TEXT[] DEFAULT '{}',
    last_calculated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(test_name, suite)
);

CREATE INDEX idx_resonance_score ON resonance_scores(score DESC);
CREATE INDEX idx_resonance_test ON resonance_scores(test_name, suite);

-- Signals table (raw observability data)
CREATE TABLE signals (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    value JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_test_id ON signals(test_id);
CREATE INDEX idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX idx_signals_type ON signals(signal_type);

-- Artifacts table
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT,
    size_bytes BIGINT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_artifacts_test_id ON artifacts(test_id);
CREATE INDEX idx_artifacts_type ON artifacts(artifact_type);
