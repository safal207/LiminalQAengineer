/**
 * LiminalQA REST API load test — k6 script
 *
 * Targets the ingest API and verifies the 1000 req/s goal.
 *
 * Usage:
 *   # Quick smoke (30s, 10 VUs)
 *   k6 run scripts/bench_rest.js
 *
 *   # Full ramp to 1000 req/s target
 *   k6 run --env TARGET_RPS=1000 scripts/bench_rest.js
 *
 *   # Against staging
 *   k6 run --env BASE_URL=http://staging:8080 --env AUTH_TOKEN=secret scripts/bench_rest.js
 *
 * Environment variables:
 *   BASE_URL     — default http://localhost:8080
 *   AUTH_TOKEN   — Bearer token (leave empty to disable auth)
 *   TARGET_RPS   — target requests per second (default 100)
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";
const TARGET_RPS = parseInt(__ENV.TARGET_RPS || "100", 10);

// VUs needed to hit TARGET_RPS at ~100ms avg response time
// VUs ≈ TARGET_RPS × avg_response_time_s
const TARGET_VUS = Math.max(1, Math.ceil(TARGET_RPS * 0.1));

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const errorRate = new Rate("liminalqa_errors");
const ingestDuration = new Trend("liminalqa_ingest_duration_ms", true);
const batchCounter = new Counter("liminalqa_batches_sent");

// ---------------------------------------------------------------------------
// Test options
// ---------------------------------------------------------------------------

export const options = {
  scenarios: {
    // Warmup: gentle ramp over 10s
    warmup: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [{ duration: "10s", target: Math.max(2, Math.ceil(TARGET_VUS * 0.2)) }],
      gracefulRampDown: "5s",
    },
    // Sustained load: hold at target for 30s
    sustained: {
      executor: "constant-vus",
      vus: TARGET_VUS,
      duration: "30s",
      startTime: "15s", // starts after warmup
    },
    // Spike: brief burst to 2× target
    spike: {
      executor: "ramping-vus",
      startVUs: TARGET_VUS,
      stages: [
        { duration: "5s", target: TARGET_VUS * 2 },
        { duration: "5s", target: TARGET_VUS },
      ],
      startTime: "50s",
      gracefulRampDown: "5s",
    },
  },

  thresholds: {
    // p95 latency < 200ms
    http_req_duration: ["p(95)<200"],
    // Error rate < 1%
    liminalqa_errors: ["rate<0.01"],
    // p99 latency < 500ms
    "http_req_duration{scenario:sustained}": ["p(99)<500"],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate a ULID-like 26-char ID (not RFC-compliant, sufficient for load test) */
function fakeUlid() {
  const chars = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
  let result = "";
  for (let i = 0; i < 26; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

function headers() {
  const h = { "Content-Type": "application/json" };
  if (AUTH_TOKEN) {
    h["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  }
  return h;
}

/**
 * Build a realistic batch payload.
 * Varies test count and statuses to exercise different code paths.
 */
function buildBatchPayload(testCount) {
  const runId = fakeUlid();
  const statuses = ["pass", "fail", "skip"];

  const tests = Array.from({ length: testCount }, (_, i) => ({
    name: `test_scenario_${i}`,
    suite: `suite_${i % 3}`,
    status: statuses[i % statuses.length],
    duration_ms: 50 + Math.floor(Math.random() * 200),
    guidance: null,
    error:
      i % statuses.length === 1
        ? { error_type: "AssertionError", message: "Expected true got false" }
        : null,
    started_at: null,
    completed_at: null,
  }));

  const signals = tests.slice(0, Math.min(2, testCount)).map((t, i) => ({
    test_name: t.name,
    kind: "api",
    latency_ms: 10 + i * 5,
    at: new Date().toISOString(),
    value: null,
    meta: { status_code: "200" },
  }));

  return {
    run: {
      run_id: runId,
      build_id: fakeUlid(),
      plan_name: "k6-bench",
      env: { CI: "true", K6: "true" },
      started_at: new Date().toISOString(),
      runner_version: "k6-bench-1.0",
    },
    tests,
    signals,
    artifacts: [],
  };
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

/** POST /ingest/batch — primary target */
function benchIngestBatch(testCount) {
  const payload = JSON.stringify(buildBatchPayload(testCount));
  const start = Date.now();

  const res = http.post(`${BASE_URL}/ingest/batch`, payload, {
    headers: headers(),
    timeout: "10s",
  });

  ingestDuration.add(Date.now() - start);
  batchCounter.add(1);

  const ok = check(res, {
    "batch: status 200": (r) => r.status === 200,
    "batch: ok=true": (r) => {
      try {
        return JSON.parse(r.body).ok === true;
      } catch {
        return false;
      }
    },
  });

  errorRate.add(!ok);
}

/** GET /health — sanity check, runs in all scenarios */
function benchHealth() {
  const res = http.get(`${BASE_URL}/health`, { timeout: "5s" });
  check(res, { "health: status 200": (r) => r.status === 200 });
}

/** GET /api/resonance/flaky — read path */
function benchFlakyQuery() {
  const res = http.get(`${BASE_URL}/api/resonance/flaky`, {
    headers: headers(),
    timeout: "10s",
  });
  check(res, { "flaky: status 200": (r) => r.status === 200 });
}

// ---------------------------------------------------------------------------
// Default function — called once per VU iteration
// ---------------------------------------------------------------------------

export default function () {
  // Mix of workloads: 70% small batch, 20% large batch, 10% reads
  const roll = Math.random();

  if (roll < 0.70) {
    benchIngestBatch(5); // small: 5 tests
  } else if (roll < 0.90) {
    benchIngestBatch(20); // larger: 20 tests
  } else if (roll < 0.95) {
    benchFlakyQuery();
  } else {
    benchHealth();
  }

  // Tiny sleep to avoid hammering in tight loops
  sleep(0.01);
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

export function setup() {
  // Verify the server is reachable before starting the test
  const res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) {
    throw new Error(
      `Server at ${BASE_URL} is not healthy (status ${res.status}). ` +
        "Start liminalqa-ingest before running k6."
    );
  }
  console.log(`✓ Server healthy at ${BASE_URL}`);
  console.log(`  Target RPS: ${TARGET_RPS}, VUs: ${TARGET_VUS}`);
  return { baseUrl: BASE_URL };
}

export function handleSummary(data) {
  const rps = data.metrics.http_reqs
    ? data.metrics.http_reqs.values.rate.toFixed(1)
    : "?";
  const p95 = data.metrics.http_req_duration
    ? data.metrics.http_req_duration.values["p(95)"].toFixed(1)
    : "?";
  const p99 = data.metrics.http_req_duration
    ? data.metrics.http_req_duration.values["p(99)"].toFixed(1)
    : "?";
  const errors = data.metrics.liminalqa_errors
    ? (data.metrics.liminalqa_errors.values.rate * 100).toFixed(2)
    : "0.00";

  const goal = parseFloat(rps) >= TARGET_RPS ? "✓ GOAL MET" : "✗ GOAL MISSED";

  console.log(`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  LiminalQA REST Benchmark Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Throughput : ${rps} req/s  (target: ${TARGET_RPS}) ${goal}
  Latency p95: ${p95} ms
  Latency p99: ${p99} ms
  Error rate : ${errors}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);

  return {
    "stdout": JSON.stringify(data, null, 2),
  };
}
