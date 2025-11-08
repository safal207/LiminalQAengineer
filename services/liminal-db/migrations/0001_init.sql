-- LIMINAL-DB Schema v1: Bi-temporal fact storage
-- Each fact has valid_from/valid_to (truth in the world) and tx_at (when we learned)

create extension if not exists btree_gist;
create extension if not exists "uuid-ossp";

-- System under test
create table system(
  system_id  uuid primary key default uuid_generate_v4(),
  name       text not null,
  version    text,
  repository text,
  created_at timestamptz not null default now()
);

-- Build artifact
create table build(
  build_id   uuid primary key default uuid_generate_v4(),
  system_id  uuid references system(system_id),
  commit_sha text not null,
  branch     text not null,
  version    text not null,
  created_at timestamptz not null default now()
);

-- Test run (hermetic execution)
create table run(
  run_id     uuid primary key,
  build_id   uuid references build(build_id),
  plan_name  text not null,
  env        jsonb not null default '{}'::jsonb,
  started_at timestamptz not null,
  ended_at   timestamptz,
  runner_version text,
  tx_at      timestamptz not null default now()
);

-- Test status enumeration
create type test_status as enum('pass','fail','xfail','flake','timeout','skip');

-- Test facts (bi-temporal)
create table test_fact(
  fact_id    bigserial primary key,
  run_id     uuid references run(run_id),
  test_name  text not null,
  suite      text not null,
  guidance   text,
  status     test_status not null,
  duration_ms integer,
  error      jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  valid_from timestamptz not null,
  valid_to   timestamptz not null default 'infinity',
  tx_at      timestamptz not null default now()
);

-- Signal types
create type signal_kind as enum('ui','api','websocket','grpc','database','network','system');

-- Signals (observations from multiple sources)
create table signal(
  signal_id  bigserial primary key,
  run_id     uuid references run(run_id),
  test_name  text,
  kind       signal_kind not null,
  latency_ms integer,
  value      double precision,
  meta       jsonb not null default '{}'::jsonb,
  at         timestamptz not null,
  tx_at      timestamptz not null default now()
);

-- Artifacts (screenshots, traces, etc.)
create type artifact_kind as enum('screenshot','api_response','ws_message','grpc_trace','log','video','trace');

create table artifact(
  artifact_id bigserial primary key,
  run_id      uuid references run(run_id),
  test_name   text,
  kind        artifact_kind not null,
  path_sha256 text not null,
  path        text not null,
  size_bytes  bigint,
  mime_type   text,
  created_at  timestamptz not null default now()
);

-- Resonance patterns (flake detection)
create table resonance(
  resonance_id bigserial primary key,
  pattern_id   uuid not null,
  description  text not null,
  score        double precision not null check (score >= 0 and score <= 1),
  occurrences  integer not null default 1,
  first_seen   timestamptz not null,
  last_seen    timestamptz not null,
  affected_tests text[] not null default '{}',
  root_cause   text,
  created_at   timestamptz not null default now()
);

comment on table test_fact is 'Bi-temporal test results with valid_from/valid_to and tx_at';
comment on table signal is 'Observations from UI/API/WS/gRPC layers';
comment on table resonance is 'Detected patterns of instability (flakes, timeouts, etc.)';
