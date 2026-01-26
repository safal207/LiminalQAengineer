-- 001_future_proof_schema.sql

CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    build_id TEXT,
    plan_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    environment JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Phase 5: Access Protocol
    protocol_version TEXT,
    self_resonance_score DOUBLE PRECISION,
    world_resonance_score DOUBLE PRECISION,
    overall_alignment_score DOUBLE PRECISION
);

CREATE TABLE tests (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    name TEXT NOT NULL,
    suite TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_message TEXT,
    stack_trace TEXT,
    metadata JSONB,
    executed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Phase 5: Access Protocol - Self Resonance
    self_resonance_score DOUBLE PRECISION,
    intent_clarity TEXT,
    resonance_frequency TEXT,
    readiness_state TEXT,

    -- Phase 5: Access Protocol - Assembly
    resonating_elements JSONB,
    filtered_noise JSONB,

    -- Phase 5: Access Protocol - Orientation
    axis_centered BOOLEAN,
    internal_direction TEXT,

    -- Phase 5: Access Protocol - Transition
    transition_smoothness DOUBLE PRECISION,
    resonance_preserved BOOLEAN,

    -- Phase 5: Access Protocol - Movement
    step_from_center BOOLEAN,
    energy_efficiency DOUBLE PRECISION,
    energy_waste DOUBLE PRECISION,

    -- Phase 5: Access Protocol - Trajectory
    trajectory_reality BOOLEAN,
    alignment_status TEXT,
    path_pattern JSONB,

    -- Phase 5: Access Protocol - World Resonance
    world_resonance_score DOUBLE PRECISION,
    mutual_influence BOOLEAN,
    feedback_count INTEGER,
    learning_count INTEGER,
    learnings JSONB
);

CREATE TABLE baselines (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    suite TEXT NOT NULL,
    mean_duration_ms DOUBLE PRECISION NOT NULL,
    stddev_duration_ms DOUBLE PRECISION NOT NULL,
    sample_size INTEGER NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Phase 5: Access Protocol Baselines
    mean_self_resonance DOUBLE PRECISION,
    mean_energy_efficiency DOUBLE PRECISION,
    mean_world_resonance DOUBLE PRECISION,

    UNIQUE(test_name, suite)
);

CREATE TABLE resonance_scores (
    id SERIAL PRIMARY KEY,
    test_name TEXT NOT NULL,
    suite TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    correlated_tests TEXT[], -- Array of strings
    last_calculated TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Phase 5: Access Protocol Correlation
    correlation_type TEXT,
    correlation_strength DOUBLE PRECISION,
    pattern_description TEXT,

    UNIQUE(test_name, suite)
);
