-- LIMINAL-DB Functions for bi-temporal operations

-- Upsert test fact (close previous version, insert new)
create or replace function upsert_test_fact(
  p_run_id uuid,
  p_test_name text,
  p_suite text,
  p_guidance text,
  p_status test_status,
  p_duration_ms int,
  p_error jsonb,
  p_started_at timestamptz,
  p_completed_at timestamptz,
  p_valid_from timestamptz
) returns bigint language plpgsql as $$
declare
  v_fact_id bigint;
begin
  -- Close any open facts for this test in this run
  update test_fact tf
     set valid_to = p_valid_from
   where tf.run_id = p_run_id
     and tf.test_name = p_test_name
     and tf.valid_to = 'infinity'::timestamptz;

  -- Insert new version
  insert into test_fact(
    run_id, test_name, suite, guidance, status,
    duration_ms, error, started_at, completed_at, valid_from
  )
  values (
    p_run_id, p_test_name, p_suite, p_guidance, p_status,
    p_duration_ms, p_error, p_started_at, p_completed_at, p_valid_from
  )
  returning fact_id into v_fact_id;

  return v_fact_id;
end $$;

-- Get current (open) test facts for a run
create or replace function get_current_test_facts(p_run_id uuid)
returns table(
  fact_id bigint,
  test_name text,
  suite text,
  status test_status,
  duration_ms int,
  valid_from timestamptz
) language sql as $$
  select fact_id, test_name, suite, status, duration_ms, valid_from
  from test_fact
  where run_id = p_run_id
    and valid_to = 'infinity'::timestamptz
  order by test_name;
$$;

-- Timeshift query: view test facts as they were at a specific moment
create or replace function timeshift_test_facts(
  p_run_id uuid,
  p_valid_at timestamptz,
  p_tx_at timestamptz default now()
)
returns table(
  fact_id bigint,
  test_name text,
  status test_status,
  duration_ms int,
  valid_from timestamptz
) language sql as $$
  select fact_id, test_name, status, duration_ms, valid_from
  from test_fact
  where run_id = p_run_id
    and tsrange(valid_from, valid_to, '[)') @> p_valid_at
    and tx_at <= p_tx_at
  order by test_name;
$$;

-- Causality walk: find signals near failed tests (±5 minutes)
create or replace function causality_walk(p_run_id uuid)
returns table(
  test_name text,
  test_failed_at timestamptz,
  signal_kind signal_kind,
  signal_at timestamptz,
  signal_value double precision,
  signal_meta jsonb,
  time_diff_seconds int
) language sql as $$
  with fails as (
    select tf.test_name, tf.completed_at as failed_at
    from test_fact tf
    where tf.run_id = p_run_id
      and tf.status in ('fail', 'timeout')
      and tf.valid_to = 'infinity'::timestamptz
  )
  select
    f.test_name,
    f.failed_at as test_failed_at,
    s.kind as signal_kind,
    s.at as signal_at,
    s.value as signal_value,
    s.meta as signal_meta,
    extract(epoch from (s.at - f.failed_at))::int as time_diff_seconds
  from fails f
  join signal s on s.run_id = p_run_id
    and s.at between f.failed_at - interval '5 minutes'
                 and f.failed_at + interval '5 minutes'
  order by f.test_name, abs(extract(epoch from (s.at - f.failed_at)));
$$;

-- Resonance map: aggregate test results by time buckets
create or replace function resonance_map(
  p_run_id uuid,
  p_bucket_interval interval default '1 minute'
)
returns table(
  bucket timestamptz,
  status test_status,
  count bigint
) language sql as $$
  select
    date_trunc('minute', tf.valid_from) as bucket,
    tf.status,
    count(*) as count
  from test_fact tf
  where tf.run_id = p_run_id
    and tf.valid_to = 'infinity'::timestamptz
  group by 1, 2
  order by 1, 2;
$$;

-- Test stability score (0 = flaky, 1 = stable)
create or replace function test_stability_score(
  p_test_name text,
  p_lookback_runs int default 10
)
returns double precision language sql as $$
  with recent_runs as (
    select distinct run_id
    from test_fact
    where test_name = p_test_name
    order by tx_at desc
    limit p_lookback_runs
  ),
  outcomes as (
    select
      tf.status,
      count(*) as cnt
    from test_fact tf
    join recent_runs rr on rr.run_id = tf.run_id
    where tf.test_name = p_test_name
      and tf.valid_to = 'infinity'::timestamptz
    group by tf.status
  )
  select
    case
      when max(cnt) = sum(cnt) then 1.0  -- all same status = stable
      else 1.0 - (count(distinct status)::double precision / sum(cnt))
    end
  from outcomes;
$$;

comment on function upsert_test_fact is 'Close previous fact version and insert new (bi-temporal update)';
comment on function timeshift_test_facts is 'Query test facts as they were at a specific valid_time and tx_time';
comment on function causality_walk is 'Find signals near failed tests to identify root causes';
comment on function resonance_map is 'Aggregate test results by time buckets for visualization';
comment on function test_stability_score is 'Calculate test stability based on recent run history';
