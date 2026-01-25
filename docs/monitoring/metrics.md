# 📈 LiminalQA Metrics Reference

## Test Execution Metrics

### liminalqa_tests_total

**Type:** Counter
**Labels:** `test_type`, `status`
**Description:** Total number of tests executed

**Example values:**
```
liminalqa_tests_total{test_type="unit", status="success"} 1523
liminalqa_tests_total{test_type="integration", status="success"} 342
liminalqa_tests_total{test_type="unit", status="failure"} 15
```

**Usage:**
```promql
# Total tests per second
rate(liminalqa_tests_total[5m])

# Tests by type
sum by (test_type) (liminalqa_tests_total)
```

---

### liminalqa_tests_passed_total

**Type:** Counter
**Labels:** `test_type`, `status`
**Description:** Total number of tests that passed

**Usage:**
```promql
# Success rate
sum(liminalqa_tests_passed_total) / sum(liminalqa_tests_total)
```

---

### liminalqa_test_failures_total

**Type:** Counter
**Labels:** `test_type`, `status`
**Description:** Total number of tests that failed

**Usage:**
```promql
# Failure rate over time
rate(liminalqa_test_failures_total[5m])
```

---

### liminalqa_test_duration_seconds

**Type:** Histogram
**Labels:** `test_type`, `status`
**Buckets:** Exponential from 1ms to ~32s
**Description:** Test execution duration in seconds

**Usage:**
```promql
# p95 latency
histogram_quantile(0.95, rate(liminalqa_test_duration_seconds_bucket[5m]))

# Average duration
rate(liminalqa_test_duration_seconds_sum[5m])
/
rate(liminalqa_test_duration_seconds_count[5m])
```

---

## System Metrics

### liminalqa_active_tests

**Type:** Gauge
**Description:** Number of currently executing tests

**Usage:**
```promql
# Current active tests
liminalqa_active_tests

# Max concurrent tests in last hour
max_over_time(liminalqa_active_tests[1h])
```

---

### liminalqa_findings_total

**Type:** Counter
**Description:** Total QA findings/issues discovered

**Usage:**
```promql
# Findings per hour
increase(liminalqa_findings_total[1h])
```

---

## Process Metrics

These are automatically exported by Rust applications:

### process_resident_memory_bytes

**Type:** Gauge
**Description:** Resident memory size in bytes

**Usage:**
```promql
# Memory in MB
process_resident_memory_bytes / 1024 / 1024
```

---

### process_cpu_seconds_total

**Type:** Counter
**Description:** Total CPU time consumed

**Usage:**
```promql
# CPU usage percentage
rate(process_cpu_seconds_total[5m]) * 100
```

---

## Labels

### test_type

Identifies the type of test being executed.

**Values:**
- `unit` - Unit tests
- `integration` - Integration tests
- `e2e` - End-to-end tests
- `performance` - Performance tests
- `security` - Security tests

### status

Test execution outcome.

**Values:**
- `success` - Test passed
- `failure` - Test failed
- `error` - Test encountered an error
- `skipped` - Test was skipped

---

## Metric Naming Conventions

LiminalQA follows Prometheus naming best practices:

- **Counters:** suffix with `_total`
- **Durations:** suffix with `_seconds`
- **Sizes:** suffix with `_bytes`
- **Prefix:** all metrics start with `liminalqa_`

---

## Recording Rules

For frequently used queries, consider adding recording rules to `prometheus.yml`:

```yaml
groups:
  - name: liminalqa_rules
    interval: 30s
    rules:
      - record: liminalqa:test_success_rate
        expr: |
          sum(rate(liminalqa_tests_passed_total[5m]))
          /
          sum(rate(liminalqa_tests_total[5m]))
```
