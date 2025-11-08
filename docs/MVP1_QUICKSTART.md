# LiminalQA MVP-1 Quickstart

Get started with LiminalQA in 5 minutes! This guide covers the full stack: bi-temporal database, REST ingest service, and reflection reports.

## 🎯 What You'll Get

- **LIMINAL-DB**: Bi-temporal PostgreSQL database with `valid_time` and `tx_time` axes
- **Ingest Service**: REST API for receiving test data
- **Reflection Reports**: Beautiful HTML reports with causality analysis
- **Selenium Grid**: Ready-to-use test execution environment
- **Demo Data**: Pre-loaded examples to explore

## 📋 Prerequisites

- Docker & Docker Compose
- curl (for testing)
- jq (optional, for pretty JSON)

## 🚀 3-Step Quickstart

### Step 1: Start Services

```bash
cd LiminalQAengineer
docker compose -f deploy/docker-compose.mvp1.yml up -d
```

This starts:
- PostgreSQL 16 with LIMINAL-DB schema
- Ingest service on port 8088
- Selenium Grid on port 4444

Wait ~10 seconds for services to be healthy:

```bash
# Check health
curl http://localhost:8088/health
```

Expected output:
```json
{
  "ok": true,
  "service": "liminal-ingest",
  "version": "0.1.0"
}
```

### Step 2: Run Demo Script

```bash
cd scripts
./demo.sh
```

This script:
1. Ingests sample data (run, tests, signals, artifacts)
2. Queries bi-temporal database
3. Shows causality walks and resonance maps

You'll see output like:

```
🚀 LiminalQA MVP-1 Demo Script
================================

📦 Step 1: Starting services...
✓ All services are healthy!

📝 Step 2: Ingesting sample data...
   → Ingesting run...
   → Ingesting tests...
   → Ingesting signals...
   → Ingesting artifacts...
✓ Sample data ingested successfully!

🔍 Step 3: Querying bi-temporal database...
   → Current test facts:
   → Causality walk (signals near failures):
   → Resonance map (test results over time):
✓ Database queries completed!

✅ Demo completed successfully!
```

### Step 3: Generate Report

```bash
# Generate HTML reflection report
docker run --rm --network liminal \
  -e LIMINAL_PG_URL=postgres://liminal:liminal@pg:5432/liminal \
  liminal-report 01HJQKX8K9N7P6R5S3T2V1W0XY \
  /tmp/report.html

# Open in browser
open /tmp/report.html  # macOS
xdg-open /tmp/report.html  # Linux
```

## 📊 Understanding the Report

The reflection report shows:

### Summary Cards
- **Pass Rate**: Overall test success percentage
- **Status Breakdown**: Passed, Failed, Flaky, Timeout, Skipped

### Top Slow Tests
- Table of slowest tests with durations
- Identifies performance bottlenecks

### Causality Trails
- **What**: Signals observed near test failures
- **Why**: Helps identify root causes (e.g., network latency spike before timeout)
- **Window**: ±5 minutes around failure time

Example trail:
```
❌ test_dashboard_load failed at 10:00:23

  network • at 10:00:20.500 (2.5s before)
    value: 4500ms latency spike

  api • at 10:00:21.000 (2s before)
    status: 504 Gateway Timeout
```

## 🔧 Manual API Testing

### Ingest a Run

```bash
curl -X POST http://localhost:8088/ingest/run \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "01HJQKX8K9N7P6R5S3T2V1W0XY",
    "build_id": "01HJQJXA9K8M7L6N5P4Q3R2S1T",
    "plan_name": "smoke-test",
    "env": {"grid": "http://selenium-hub:4444"},
    "started_at": "2025-10-31T10:00:00Z",
    "runner_version": "0.1.0"
  }'
```

### Ingest Tests

```bash
curl -X POST http://localhost:8088/ingest/tests \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "01HJQKX8K9N7P6R5S3T2V1W0XY",
    "valid_from": "2025-10-31T10:03:00Z",
    "tests": [
      {
        "name": "test_example",
        "suite": "smoke",
        "guidance": "System should respond",
        "status": "pass",
        "duration_ms": 1234,
        "started_at": "2025-10-31T10:00:15Z",
        "completed_at": "2025-10-31T10:00:16.234Z"
      }
    ]
  }'
```

### Ingest Signals

```bash
curl -X POST http://localhost:8088/ingest/signals \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "01HJQKX8K9N7P6R5S3T2V1W0XY",
    "signals": [
      {
        "kind": "api",
        "latency_ms": 120,
        "value": 200,
        "meta": {"endpoint": "/api/health"},
        "at": "2025-10-31T10:00:15.250Z"
      }
    ]
  }'
```

## 🔍 Querying LIMINAL-DB

### Connect to Database

```bash
docker exec -it liminal-postgres psql -U liminal -d liminal
```

### Example Queries

#### Current Test Facts (Open Interval)

```sql
SELECT test_name, status, duration_ms
FROM test_fact
WHERE run_id = '01HJQKX8K9N7P6R5S3T2V1W0XY'
  AND valid_to = 'infinity'
ORDER BY test_name;
```

#### Timeshift Query (View Past State)

```sql
SELECT test_name, status, duration_ms
FROM timeshift_test_facts(
  '01HJQKX8K9N7P6R5S3T2V1W0XY',
  '2025-10-31 10:05:00',
  '2025-10-31 10:06:00'
);
```

#### Causality Walk (Find Root Causes)

```sql
SELECT test_name, signal_kind, signal_at, time_diff_seconds
FROM causality_walk('01HJQKX8K9N7P6R5S3T2V1W0XY')
LIMIT 10;
```

#### Resonance Map (Flake Detection)

```sql
SELECT bucket, status, count
FROM resonance_map('01HJQKX8K9N7P6R5S3T2V1W0XY');
```

#### Test Stability Score

```sql
SELECT test_stability_score('test_login_success', 10) as score;
-- Returns 0.0 (flaky) to 1.0 (stable)
```

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────┐
│  Test Runner (your code)                    │
│  • Executes tests                           │
│  • Records signals                          │
└──────────────────┬──────────────────────────┘
                   │ HTTP POST
                   ▼
┌─────────────────────────────────────────────┐
│  Liminal Ingest Service (port 8088)         │
│  • REST API with Bearer auth                │
│  • Validates & persists data                │
└──────────────────┬──────────────────────────┘
                   │ SQL
                   ▼
┌─────────────────────────────────────────────┐
│  LIMINAL-DB (PostgreSQL)                    │
│  • Bi-temporal tables                       │
│  • valid_time × tx_time                     │
│  • Causality functions                      │
└──────────────────┬──────────────────────────┘
                   │ Query
                   ▼
┌─────────────────────────────────────────────┐
│  Liminal Report Generator                   │
│  • Queries aggregated data                  │
│  • Renders HTML with causality trails       │
└─────────────────────────────────────────────┘
```

## 🔐 Configuration

### Environment Variables

#### Ingest Service

- `LIMINAL_PG_URL`: Database connection string (default: `postgres://liminal:liminal@pg:5432/liminal`)
- `LIMINAL_API_TOKEN`: Bearer token for authentication (default: `devtoken`)
- `LIMINAL_BIND_ADDR`: Bind address (default: `0.0.0.0:8088`)
- `RUST_LOG`: Logging level (default: `info`)

#### Report Generator

- `LIMINAL_PG_URL`: Database connection string

### Changing API Token

```bash
# In docker-compose.mvp1.yml
environment:
  LIMINAL_API_TOKEN: your-secret-token-here

# Then use it in requests
curl -H "Authorization: Bearer your-secret-token-here" ...
```

## 📝 Next Steps

### Integrate with Your Tests

1. **Send run metadata** when test suite starts:
   ```
   POST /ingest/run
   ```

2. **Send test results** as they complete:
   ```
   POST /ingest/tests
   ```

3. **Send signals** during test execution:
   ```
   POST /ingest/signals (UI clicks, API calls, etc.)
   ```

4. **Send artifacts** (screenshots, traces):
   ```
   POST /ingest/artifacts
   ```

5. **Generate report** after run completes:
   ```
   liminal-report <run-id> output.html
   ```

### CI/CD Integration

#### GitHub Actions

```yaml
- name: Run LiminalQA tests
  run: |
    # Start services
    docker compose -f deploy/docker-compose.mvp1.yml up -d

    # Run your tests (they POST to localhost:8088)
    npm test

    # Generate report
    docker run --network liminal liminal-report $RUN_ID report.html

    # Upload artifact
    - uses: actions/upload-artifact@v3
      with:
        name: liminal-report
        path: report.html
```

#### GitLab CI

```yaml
test:
  services:
    - postgres:16
  script:
    - docker compose -f deploy/docker-compose.mvp1.yml up -d
    - npm test
    - liminal-report $RUN_ID report.html
  artifacts:
    paths:
      - report.html
```

## 🐛 Troubleshooting

### Services won't start

```bash
# Check logs
docker compose -f deploy/docker-compose.mvp1.yml logs

# Restart services
docker compose -f deploy/docker-compose.mvp1.yml down
docker compose -f deploy/docker-compose.mvp1.yml up -d
```

### Database connection failed

```bash
# Check PostgreSQL is healthy
docker exec liminal-postgres pg_isready

# Check migrations applied
docker exec liminal-postgres psql -U liminal -d liminal -c "\dt"
```

### Ingest service returns 401 Unauthorized

Check your `Authorization` header includes `Bearer <token>` and matches `LIMINAL_API_TOKEN`.

### Report generation fails

```bash
# Check run exists in database
docker exec liminal-postgres psql -U liminal -d liminal -c \
  "SELECT * FROM run WHERE run_id = '<your-run-id>';"
```

## 📚 Learn More

- [Architecture Deep Dive](ARCHITECTURE.md)
- [API Reference](API_REFERENCE.md)
- [Bi-Temporal Queries](BITEMPORAL_QUERIES.md)

## 🤝 Support

- Issues: https://github.com/safal207/LiminalQAengineer/issues
- Discussions: https://github.com/safal207/LiminalQAengineer/discussions

---

**🧠 LiminalQA — превращаем QA в систему памяти и причинности**
