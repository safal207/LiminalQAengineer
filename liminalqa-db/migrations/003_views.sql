-- 003_views.sql

CREATE VIEW view_recent_runs AS
SELECT
    id, plan_name, status, started_at, duration_ms,
    (SELECT COUNT(*) FROM tests WHERE run_id = runs.id AND status = 'passed') as passed_count,
    (SELECT COUNT(*) FROM tests WHERE run_id = runs.id AND status = 'failed') as failed_count,
    (SELECT COUNT(*) FROM tests WHERE run_id = runs.id AND status = 'skipped') as skipped_count
FROM runs
ORDER BY started_at DESC;

-- Phase 5 View: Protocol Quality
CREATE VIEW view_protocol_quality AS
SELECT
    id, name, suite, status, duration_ms,
    self_resonance_score, energy_efficiency,
    world_resonance_score,
    (
        COALESCE(self_resonance_score, 0.5) * 0.3 +
        COALESCE(energy_efficiency, 0.5) * 0.2 +
        COALESCE(world_resonance_score, 0.5) * 0.3 +
        CASE WHEN trajectory_reality THEN 0.2 ELSE 0 END
    ) as overall_protocol_quality
FROM tests
WHERE self_resonance_score IS NOT NULL;
