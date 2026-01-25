# 📊 LiminalQA Monitoring Guide

## Overview

LiminalQA uses Prometheus for metrics collection and Grafana for visualization.

## Quick Start

### Start Monitoring Stack

```bash
cd deploy
docker-compose -f docker-compose.monitoring.yml up -d
```

### Access Dashboards

- **Grafana:** http://localhost:3000
  - Username: `admin`
  - Password: `admin` (change on first login!)

- **Prometheus:** http://localhost:9090

### Stop Monitoring

```bash
docker-compose -f docker-compose.monitoring.yml down
```

## Architecture

```
┌──────────────┐
│ LiminalQA    │──┐
│ Runner       │  │
└──────────────┘  │
                  │  /metrics
┌──────────────┐  │  endpoint
│ LiminalQA    │──┤
│ Ingest       │  │
└──────────────┘  │
                  │
                  ▼
            ┌──────────────┐
            │  Prometheus  │
            │  (collector) │
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │   Grafana    │
            │ (dashboard)  │
            └──────────────┘
```

## Available Metrics

See [metrics.md](./metrics.md) for detailed metric descriptions.

### Key Metrics

- `liminalqa_tests_total` - Total tests executed
- `liminalqa_tests_passed_total` - Successful tests
- `liminalqa_test_failures_total` - Failed tests
- `liminalqa_test_duration_seconds` - Test execution time
- `liminalqa_active_tests` - Currently running tests
- `liminalqa_findings_total` - QA issues found

## Alerts

See [alerts.md](./alerts.md) for alert descriptions.

### Critical Alerts

- **ServiceDown**: Service is unreachable
- **HighErrorRate**: >10% test failure rate
- **SlowTestExecution**: p95 latency >30s

## Grafana Dashboards

### Main Dashboard

The main LiminalQA dashboard shows:

1. **Test Execution Rate** - Tests/second over time
2. **Success Rate** - Percentage of passing tests
3. **Duration Percentiles** - p50, p95, p99 latencies
4. **Active Tests** - Current concurrent tests
5. **Daily Statistics** - Total tests and failures
6. **Resource Usage** - Memory and CPU

### Custom Dashboards

To create custom dashboards:

1. Login to Grafana (http://localhost:3000)
2. Click "+" → "Dashboard"
3. Add panels with PromQL queries
4. Save dashboard

## Querying Metrics

### Example PromQL Queries

**Test success rate:**
```promql
sum(rate(liminalqa_tests_passed_total[5m]))
/
sum(rate(liminalqa_tests_total[5m]))
```

**Average test duration:**
```promql
rate(liminalqa_test_duration_seconds_sum[5m])
/
rate(liminalqa_test_duration_seconds_count[5m])
```

**Tests by type:**
```promql
sum by (test_type) (rate(liminalqa_tests_total[5m]))
```

## Troubleshooting

### Metrics not appearing

1. Check service is running: `docker ps`
2. Verify `/metrics` endpoint: `curl http://localhost:8080/metrics`
3. Check Prometheus targets: http://localhost:9090/targets

### Dashboard not loading

1. Verify Grafana datasource configuration
2. Check Prometheus connectivity
3. Review Grafana logs: `docker logs liminalqa-grafana`

### High memory usage

Prometheus stores metrics in memory. If using too much:

1. Reduce retention time in `prometheus.yml`
2. Decrease scrape interval
3. Add resource limits in docker-compose

## Production Deployment

For production:

1. **Change default passwords**
2. **Enable authentication** on Prometheus
3. **Set up persistent storage** for metrics
4. **Configure alerting** (Alertmanager)
5. **Use HTTPS** with reverse proxy
6. **Set retention policy** based on needs

## Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)
