-- migrations/001_future_proof_schema.sql

-- ============================================================================
-- RUNS TABLE (Test Executions)
-- ============================================================================
CREATE TABLE runs (
    -- Core fields (Phase 4)
    id TEXT PRIMARY KEY,
    build_id TEXT,
    plan_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'passed', 'failed', 'error')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    environment JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Access Protocol fields (Phase 5 - reserved)
    protocol_version TEXT,  -- 'v1.0' when Phase 5 starts
    self_resonance_score REAL CHECK (self_resonance_score >= 0 AND self_resonance_score <= 1),
    world_resonance_score REAL CHECK (world_resonance_score >= 0 AND world_resonance_score <= 1),
    overall_alignment_score REAL CHECK (overall_alignment_score >= 0 AND overall_alignment_score <= 1)
);

CREATE INDEX idx_runs_started_at ON runs(started_at DESC);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_plan_name ON runs(plan_name);
CREATE INDEX idx_runs_resonance ON runs(self_resonance_score DESC) WHERE self_resonance_score IS NOT NULL;

-- ============================================================================
-- TESTS TABLE (Individual Test Results)
-- ============================================================================
CREATE TABLE tests (
    -- Core fields (Phase 4)
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    suite TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'skipped', 'error', 'xfail', 'flake', 'timeout')), -- Added xfail, flake, timeout based on TestStatus enum
    duration_ms INTEGER NOT NULL,
    error_message TEXT,
    stack_trace TEXT,
    metadata JSONB,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Access Protocol fields (Phase 5 - reserved)
    -- Self Resonance (Phase 0)
    self_resonance_score REAL CHECK (self_resonance_score >= 0 AND self_resonance_score <= 1),
    intent_clarity TEXT,  -- The "why" behind the test
    resonance_frequency TEXT CHECK (resonance_frequency IN ('high', 'centered', 'low')),
    readiness_state TEXT CHECK (readiness_state IN ('aligned', 'checking', 'misaligned')),

    -- Assembly (Phase 2)
    resonating_elements JSONB,  -- What was accepted
    filtered_noise JSONB,       -- What was discarded

    -- Orientation (Phase 3)
    axis_centered BOOLEAN,
    internal_direction TEXT CHECK (internal_direction IN ('aligned', 'exploring', 'reactive')),

    -- Transition (Phase 4)
    transition_smoothness REAL CHECK (transition_smoothness >= 0 AND transition_smoothness <= 1),
    resonance_preserved BOOLEAN,

    -- Movement (Phase 5)
    step_from_center BOOLEAN,
    energy_efficiency REAL CHECK (energy_efficiency >= 0 AND energy_efficiency <= 1),
    energy_waste REAL,

    -- Trajectory (Phase 6)
    trajectory_reality BOOLEAN,  -- Real path vs illusion
    alignment_status TEXT CHECK (alignment_status IN ('aligned', 'checking', 'illusion')),
    path_pattern JSONB,

    -- World Resonance (Phase 7)
    world_resonance_score REAL CHECK (world_resonance_score >= 0 AND world_resonance_score <= 1),
    mutual_influence BOOLEAN,
    feedback_count INTEGER DEFAULT 0,
    learning_count INTEGER DEFAULT 0,
    learnings JSONB,

    -- Overall Protocol Quality
    protocol_cycle_valid BOOLEAN,
    protocol_validation_errors JSONB
);

CREATE INDEX idx_tests_run_id ON tests(run_id);
CREATE INDEX idx_tests_name_suite ON tests(name, suite);
CREATE INDEX idx_tests_executed_at ON tests(executed_at DESC);
CREATE INDEX idx_tests_status ON tests(status);

-- Access Protocol indexes (for Phase 5)
CREATE INDEX idx_tests_self_resonance ON tests(self_resonance_score DESC) WHERE self_resonance_score IS NOT NULL;
CREATE INDEX idx_tests_trajectory_reality ON tests(trajectory_reality) WHERE trajectory_reality IS NOT NULL;
CREATE INDEX idx_tests_energy_efficiency ON tests(energy_efficiency DESC) WHERE energy_efficiency IS NOT NULL;
CREATE INDEX idx_tests_world_resonance ON tests(world_resonance_score DESC) WHERE world_resonance_score IS NOT NULL;

-- ============================================================================
-- BASELINES TABLE (Drift Detection)
-- ============================================================================
CREATE TABLE baselines (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    suite TEXT NOT NULL,
    mean_duration_ms DOUBLE PRECISION NOT NULL,
    stddev_duration_ms DOUBLE PRECISION NOT NULL,
    sample_size INTEGER NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Access Protocol baseline metrics (Phase 5)
    mean_self_resonance REAL,
    mean_energy_efficiency REAL,
    mean_world_resonance REAL,

    UNIQUE(test_name, suite)
);

CREATE INDEX idx_baselines_test_suite ON baselines(test_name, suite);

-- ============================================================================
-- RESONANCE_SCORES TABLE (Pattern Detection)
-- ============================================================================
CREATE TABLE resonance_scores (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    suite TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
    correlated_tests TEXT[] DEFAULT '{}',
    last_calculated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Access Protocol correlation data (Phase 5)
    correlation_type TEXT,  -- 'temporal', 'causal', 'resonant'
    correlation_strength REAL,
    pattern_description TEXT,

    UNIQUE(test_name, suite)
);

CREATE INDEX idx_resonance_score ON resonance_scores(score DESC);
CREATE INDEX idx_resonance_test ON resonance_scores(test_name, suite);

-- ============================================================================
-- PROTOCOL_CYCLES TABLE (Phase 5 - Full Protocol Tracking)
-- ============================================================================
CREATE TABLE protocol_cycles (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    cycle_number INTEGER NOT NULL,  -- Tests can have multiple cycles

    -- Cycle timestamps
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,

    -- Phase-by-phase data
    self_resonance JSONB,    -- Phase 0 data
    access_point JSONB,      -- Phase 1 data
    assembly JSONB,          -- Phase 2 data
    orientation JSONB,       -- Phase 3 data
    transition JSONB,        -- Phase 4 data
    movement JSONB,          -- Phase 5 data
    trajectory JSONB,        -- Phase 6 data
    world_resonance JSONB,   -- Phase 7 data

    -- Validation
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    validation_errors JSONB,

    -- Metrics
    overall_quality_score REAL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(test_id, cycle_number)
);

CREATE INDEX idx_protocol_cycles_test_id ON protocol_cycles(test_id);
CREATE INDEX idx_protocol_cycles_quality ON protocol_cycles(overall_quality_score DESC) WHERE overall_quality_score IS NOT NULL;

-- ============================================================================
-- SIGNALS TABLE (Raw Observability Data)
-- ============================================================================
CREATE TABLE signals (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    value JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Access Protocol signal classification (Phase 5)
    protocol_phase TEXT,  -- Which phase generated this signal
    resonance_contribution REAL  -- How much this affects resonance
);

CREATE INDEX idx_signals_test_id ON signals(test_id);
CREATE INDEX idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX idx_signals_type ON signals(signal_type);
CREATE INDEX idx_signals_protocol_phase ON signals(protocol_phase) WHERE protocol_phase IS NOT NULL;

-- ============================================================================
-- ARTIFACTS TABLE (Test Artifacts)
-- ============================================================================
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

-- ============================================================================
-- VIEWS (Convenience queries)
-- ============================================================================

-- View: Tests with Protocol Quality (Phase 5)
CREATE VIEW tests_with_protocol_quality AS
SELECT
    t.id,
    t.name,
    t.suite,
    t.status,
    t.duration_ms,
    t.self_resonance_score,
    t.energy_efficiency,
    t.trajectory_reality,
    t.world_resonance_score,
    t.mutual_influence,
    t.learning_count,
    -- Computed overall quality
    CASE
        WHEN t.self_resonance_score IS NULL THEN NULL
        ELSE (
            COALESCE(t.self_resonance_score, 0.5) * 0.3 +
            COALESCE(t.energy_efficiency, 0.5) * 0.2 +
            COALESCE(t.world_resonance_score, 0.5) * 0.3 +
            CASE WHEN t.trajectory_reality THEN 0.2 ELSE 0 END
        )
    END as overall_protocol_quality
FROM tests t;

-- View: Protocol Health Dashboard
CREATE VIEW protocol_health_dashboard AS
SELECT
    DATE(executed_at) as date,
    COUNT(*) as total_tests,
    AVG(self_resonance_score) as avg_self_resonance,
    AVG(energy_efficiency) as avg_energy_efficiency,
    AVG(world_resonance_score) as avg_world_resonance,
    SUM(CASE WHEN trajectory_reality THEN 1 ELSE 0 END) as real_trajectories,
    SUM(CASE WHEN NOT trajectory_reality THEN 1 ELSE 0 END) as illusion_trajectories,
    SUM(learning_count) as total_learnings
FROM tests
WHERE executed_at > NOW() - INTERVAL '30 days'
  AND self_resonance_score IS NOT NULL
GROUP BY DATE(executed_at)
ORDER BY date DESC;
