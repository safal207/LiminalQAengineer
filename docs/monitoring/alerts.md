# 🔔 LiminalQA Alerts Reference

## Overview

This document describes all configured alerts for LiminalQA monitoring.

## Alert Severity Levels

- **🔴 Critical:** Requires immediate attention, service degradation
- **🟡 Warning:** Potential issue, monitor closely
- **🔵 Info:** Informational, no action required

---

## Critical Alerts

### ServiceDown

**Severity:** 🔴 Critical
**Trigger:** Service has been down for >1 minute
**Expression:**
```promql
up{job=~"liminalqa.*"} == 0
```

**What it means:**
A LiminalQA service is not responding to health checks.

**Actions:**
1. Check if service is running: `docker ps | grep liminalqa`
2. View logs: `docker logs <container-name>`
3. Restart service if needed: `docker-compose restart <service>`
4. Check network connectivity
5. Review recent deployments

**Prevention:**
- Implement proper health checks
- Use graceful shutdown procedures
- Monitor resource usage

---

## Warning Alerts

### HighErrorRate

**Severity:** 🟡 Warning
**Trigger:** >10% test failure rate for >5 minutes
**Expression:**
```promql
(
  rate(liminalqa_test_failures_total[5m])
  /
  rate(liminalqa_tests_total[5m])
) > 0.1
```

**What it means:**
More than 10% of tests are failing, indicating potential issues with:
- Test environment
- Application under test
- Test infrastructure

**Actions:**
1. Check recent test results in dashboard
2. Review failed test logs
3. Verify test environment configuration
4. Check for infrastructure changes
5. Review recent code deployments

**Prevention:**
- Implement test quarantine for flaky tests
- Monitor test environment stability
- Use canary deployments

---

### SlowTestExecution

**Severity:** 🟡 Warning
**Trigger:** p95 test duration >30s for >10 minutes
**Expression:**
```promql
histogram_quantile(0.95,
  rate(liminalqa_test_duration_seconds_bucket[5m])
) > 30
```

**What it means:**
95% of tests are taking longer than 30 seconds to execute.

**Possible causes:**
- Database performance degradation
- Network latency issues
- Resource contention
- Inefficient test implementation

**Actions:**
1. Check system resource usage (CPU, Memory, I/O)
2. Review slow query logs
3. Analyze test performance metrics
4. Check for concurrent test execution issues
5. Profile slow tests

**Prevention:**
- Set test timeout limits
- Optimize database queries
- Use test parallelization wisely
- Monitor resource allocation

---

### HighMemoryUsage

**Severity:** 🟡 Warning
**Trigger:** Memory usage >1GB for >5 minutes
**Expression:**
```promql
(
  process_resident_memory_bytes{job=~"liminalqa.*"}
  / 1024 / 1024
) > 1024
```

**What it means:**
A service is consuming more than 1GB of memory.

**Possible causes:**
- Memory leak
- Large dataset processing
- Insufficient garbage collection
- Resource-intensive operations

**Actions:**
1. Check memory usage trends in Grafana
2. Review service logs for errors
3. Analyze heap dumps if available
4. Check for memory leaks
5. Consider increasing memory limits or optimizing code

**Prevention:**
- Implement memory usage monitoring
- Set appropriate resource limits
- Use streaming for large datasets
- Profile memory usage regularly

---

## Info Alerts

### NoTestActivity

**Severity:** 🔵 Info
**Trigger:** No tests executed for >15 minutes
**Expression:**
```promql
rate(liminalqa_tests_total[10m]) == 0
```

**What it means:**
No test activity detected. This might be normal (off-hours) or indicate:
- Test pipeline stopped
- Scheduler issues
- Configuration problems

**Actions:**
1. Verify if this is expected (maintenance window, off-hours)
2. Check test scheduler status
3. Review CI/CD pipeline logs
4. Verify test trigger configuration

**Prevention:**
- Schedule regular test runs
- Set up test pipeline monitoring
- Configure expected test frequency

---

## Alert Configuration

### Prometheus Alertmanager

To send alerts to external systems, configure Alertmanager:

**File:** `deploy/prometheus/alertmanager.yml`

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'team-notifications'

receivers:
  - name: 'team-notifications'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#liminalqa-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
        description: '{{ .GroupLabels.alertname }}'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'service']
```

---

##Silencing Alerts

### Temporary Silence

During maintenance:

```bash
# Using Prometheus UI
1. Go to http://localhost:9090/alerts
2. Click "Silence" next to alert
3. Set duration and reason
4. Click "Create"

# Using amtool CLI
amtool silence add alertname=HighErrorRate \
  --duration=2h \
  --comment="Planned maintenance"
```

---

## Custom Alerts

### Adding New Alerts

1. Edit `deploy/prometheus/alerts.yml`
2. Add new rule to appropriate group:

```yaml
- alert: CustomAlert
  expr: your_promql_query
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Brief description"
    description: "Detailed description with {{ $value }}"
```

3. Reload Prometheus configuration:
```bash
curl -X POST http://localhost:9090/-/reload
```

4. Verify alert: http://localhost:9090/alerts

---

## Alert Testing

### Test Alert Firing

```bash
# Manually trigger alert condition
# Example: Stop a service
docker stop liminalqa-runner

# Wait for alert to fire (check for: duration)
# Verify in Prometheus UI
```

### Alert Rule Validation

```bash
# Validate alert rules syntax
promtool check rules deploy/prometheus/alerts.yml

# Test alert query
promtool query instant http://localhost:9090 \
  'up{job=~"liminalqa.*"} == 0'
```

---

## Alert Runbook Template

When creating new alerts, document the response:

```yaml
- alert: NewAlert
  expr: metric > threshold
  for: 5m
  annotations:
    summary: "What happened"
    description: "Details with {{ $value }}"
    runbook_url: "https://wiki.company.com/runbooks/newalert"
```

**Runbook should include:**
1. Alert description
2. Impact on users
3. Troubleshooting steps
4. Resolution procedures
5. Prevention measures

---

## Best Practices

### Alert Design

✅ **DO:**
- Set appropriate `for:` duration to avoid flapping
- Include helpful context in annotations
- Use severity levels consistently
- Test alerts before deploying
- Document response procedures

❌ **DON'T:**
- Alert on symptoms without actionability
- Set overly sensitive thresholds
- Create too many alerts (alert fatigue)
- Forget to update alerts when systems change

### Alert Hygiene

- Review alerts monthly
- Remove obsolete alerts
- Update thresholds based on baselines
- Track alert response times
- Document false positive patterns

---

## Monitoring the Monitoring

### Meta-Alerts

Alert when monitoring itself has issues:

```yaml
- alert: PrometheusDown
  expr: up{job="prometheus"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Prometheus is down"

- alert: PrometheusTooManyRestarts
  expr: changes(process_start_time_seconds{job="prometheus"}[15m]) > 2
  labels:
    severity: warning
  annotations:
    summary: "Prometheus restarting frequently"
```

---

## Resources

- [Prometheus Alerting](https://prometheus.io/docs/alerting/latest/overview/)
- [Alert Rule Best Practices](https://prometheus.io/docs/practices/alerting/)
- [PromQL for Alerting](https://prometheus.io/docs/prometheus/latest/querying/basics/)
