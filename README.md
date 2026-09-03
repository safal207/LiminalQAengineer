# LiminalQA

[![CI](https://github.com/safal207/LiminalQAengineer/workflows/CI/badge.svg)](https://github.com/safal207/LiminalQAengineer/actions/workflows/ci.yml)
[![Security Audit](https://github.com/safal207/LiminalQAengineer/workflows/Security%20Audit/badge.svg)](https://github.com/safal207/LiminalQAengineer/actions/workflows/security-audit.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Documentation: [English](https://github.com/safal207/ContractGraph-QA/blob/3ff86db99ecb0eeae7fa4b517ac7c8a157a2441a/docs/i18n/en/GETTING_STARTED.md) · [简体中文](https://github.com/safal207/ContractGraph-QA/blob/3ff86db99ecb0eeae7fa4b517ac7c8a157a2441a/docs/i18n/zh-CN/GETTING_STARTED.md) · [हिन्दी](https://github.com/safal207/ContractGraph-QA/blob/3ff86db99ecb0eeae7fa4b517ac7c8a157a2441a/docs/i18n/hi/GETTING_STARTED.md) · [Español](https://github.com/safal207/ContractGraph-QA/blob/3ff86db99ecb0eeae7fa4b517ac7c8a157a2441a/docs/i18n/es/GETTING_STARTED.md) · [العربية](https://github.com/safal207/ContractGraph-QA/blob/3ff86db99ecb0eeae7fa4b517ac7c8a157a2441a/docs/i18n/ar/GETTING_STARTED.md)

> **From raw test outcomes to actionable quality decisions.**

---

## Why this exists

Every team runs tests. Most teams get a red/green result and then spend 30–60 minutes answering the same questions manually:

- Is this a real bug or a flake?
- Did this test fail because of *my* change or an infrastructure issue?
- Should I block the merge or let it through with a warning?
- What have other teams done when they saw the same pattern?

**LiminalQA answers all four questions automatically, before the engineer even opens the CI log.**

It does this by combining:

| Signal | What it detects |
|--------|-----------------|
| EMA baselines + trend analysis | Duration degradation, timeout drift |
| Flake probability model | Tests that fail non-deterministically |
| Triage engine | New bug vs flake vs known issue vs stable |
| Root-cause analysis | Infra flake / regression / test design / external dep |
| Counterfactual reasoning | "If we fixed the infra issue, pass rate goes from 70% → 94%" |
| Community pattern matching | "12 other projects had the same pattern — here's what worked" |

The result is a structured **decision packet** — readable by humans, consumable by GitHub Action bots and AI agents (Claude, Copilot) in a single tool call.

### The gap LiminalQA fills

```
  CI shows red
       │
       ▼
  ┌─────────────────────────────────────────────┐
  │  ← this gap costs ~30–60 min per incident   │  ← LiminalQA lives here
  │                                             │
  │  Is it a flake?  New bug?  Known issue?     │
  │  Who owns it?  Should I retry?  Block PR?   │
  └─────────────────────────────────────────────┘
       │
       ▼
  Engineer knows what to do
```

### What it looks like in practice

```
cargo test -p liminalqa-core --test dashboard_demo -- --nocapture
```

```
╔════════════════════════════════════════════════════════════════════╗
║  LIMINALQA · payments/charge_card                                  ║
╚════════════════════════════════════════════════════════════════════╝

┌─ A  TEST RISK CARD ────────────────────────────────────────────────┐
│  verdict:        ⚠ FLAKE                confidence:  80%           │
│  severity:       HIGH                   merge:  🟡 WARN             │
│  action:         retry_with_backoff     trend:  ↗ degrading        │
│  flake risk:     ████████████████░░░░ 82%                          │
│  timeout:        0.7s (EMA mean + 3σ)                              │
│  insight:        Test oscillates between pass and fail (70% stab…  │
└────────────────────────────────────────────────────────────────────┘

┌─ B  ROOT CAUSE ANALYSIS ───────────────────────────────────────────┐
│  most likely:    infrastructure_flake (44%)                         │
│  ▶ infrastructure_flake      ███████░░░░░░░░░░░  44%               │
│    · high flake probability (82%)                                   │
│    · triage verdict: flake                                          │
│  ▶ code_regression           ███░░░░░░░░░░░░░░░  19%               │
│  fix:  Add retry logic with exponential backoff                     │
└────────────────────────────────────────────────────────────────────┘

┌─ C  WHAT-IF  /  COUNTERFACTUAL ────────────────────────────────────┐
│  current pass rate    ██████████████░░░░░░  70%                     │
│  if infra flake fixed      ██████████████████░░  94%  (+24pp)       │
│  if code regression fixed  ████████████████░░░░  80%  (+10pp)       │
└────────────────────────────────────────────────────────────────────┘

┌─ D  COMMUNITY INSIGHTS ────────────────────────────────────────────┐
│  matches:  1 similar incident in community knowledge base           │
│  ▶ similarity 99%   seen in 4 project(s)                            │
│    action:  Add retry with exponential backoff                      │
│    effective: █████░░░░░ 50% of reporters resolved with this action │
└────────────────────────────────────────────────────────────────────┘
```

---

## Case studies

### Case 1: Flaky payment test — 25-minute investigation → 2 seconds

A `payments/charge_card` test was failing 30% of the time.  Engineers spent
25–40 minutes per incident deciding: real bug or flake?  Should we block?

LiminalQA analysed 30 runs and returned in 2 seconds:
**verdict `FLAKE`, confidence 80%, merge policy `🟡 WARN`** — with root cause
ranked as `infrastructure_flake (44%)` and a counterfactual showing that fixing
the infra issue would raise pass rate from **70% → 94%**.

Result: false merge blocks dropped from **3–5/week to 0–1**.
[Read the full case study →](docs/case-studies/flaky-ci-bottleneck.md)

---

### Case 2: Silent regression — caught in 2 seconds, not 6 hours

A routine refactor of token validation logic passed all checks and was merged.
Six hours later, 8% of API calls were returning 401.

With LiminalQA, the CI would have shown:
**verdict `NEW_BUG`, severity `CRITICAL`, merge policy `🔴 BLOCK`** — before
any human reviewed the PR.  Evidence: the test had a 99% pass rate over 25
runs, then failed 3 consecutive times with only 5% flake probability.

Result: regression caught **pre-merge** instead of post-incident.
[Read the full case study →](docs/case-studies/regression-critical-path.md)

---

## 🎯 Философия LIMINAL

```
Guidance → Co-Navigation → Inner Council → Reflection
```

1. **Guidance** — намерение теста (что хотим увидеть в системе)
2. **Co-Navigation** — выполнение с адаптацией (ретраи, тайм-боксы, "гибкие ожидания")
3. **Inner Council** — согласование сигналов (UI/API/WS/gRPC) в единую картину
4. **Reflection** — отчёт как история причинности, а не просто список падений

## 🏗️ Архитектура

```
┌──────────────────────────────────────────────────────────────────┐
│                         LiminalOS (минимум)                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Supervisor/Init  •  Isolated Runners  •  Net Sandbox      │  │
│  │  • hermetic deps  • reproducible envs (Nix/OCI)            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                 ↑                                  ↑             │
│                 │                                  │             │
│        liminalqa-rs Runner                   Observability        │
│     (Guidance→Co-Nav→Council→Reflection)      (tracing)           │
│                 │                                  │             │
│                 └──────────► Event Log & State ◄───┘             │
├──────────────────────────────────────────────────────────────────┤
│                     LIMINAL-DB (bi-temporal)                      │
│  Entities: System, Build, Run, Test, Artifact, Signal, Resonance │
│  Facts: :test/status, :test/duration, :ws/latency, :ui/screenshot │
│  Axes: valid_time  &  transaction_time                            │
│  Query: Datalog-like (pull/where), Timeshift, Causality Walks     │
└──────────────────────────────────────────────────────────────────┘
```

## 📦 Модули

- **liminalqa-core** — Типы данных, entities, facts, би-темпоральная модель
- **liminalqa-db** — Хранилище с двумя осями времени (valid_time × tx_time)
- **liminalqa-runner** — Движок тестов (Guidance → Reflection)
- **liminalqa-ingest** — REST API для приёма данных о прогонах
- **limctl** — CLI для управления прогонами и генерации отчётов

Файловый адаптер [ContractGraph-QA interoperability v0.1](docs/CGQA_INTEROP.md)
принимает bounded evidence без подмены статусов и экспортирует только
неавторитетные candidates для независимого CGQA replay.

Общий interop-hub также даёт consumer SDK для TypeScript/JavaScript, Go,
Java/JVM и .NET. Вместе с нативными runners на Python, Rust и Elixir это восемь
языковых экосистем с одним pinned contract и без смешения verdict authority:
[SDK matrix](https://github.com/safal207/ContractGraph-QA/blob/3ff86db99ecb0eeae7fa4b517ac7c8a157a2441a/sdks/README.md).

## 🚀 Быстрый старт

### Docker-развертывание (рекомендуется)

Для решения проблем с компиляцией на Windows используйте Docker:

```bash
# Сборка и запуск в Docker
docker build -t liminalqa .
docker run -it --rm -v $(pwd)/data:/app/data -v $(pwd)/reports:/app/reports liminalqa

# Или с использованием docker-compose
docker-compose up liminalqa-build
```

### Локальная разработка (Linux/macOS)

```bash
# Инициализация проекта
cargo run --bin limctl -- init my-project
cd my-project

# Запуск ingest сервера
cargo run --bin liminalqa-ingest

# Запуск тестов
cargo run --bin limctl -- run plans/example.yaml

# Просмотр runs
cargo run --bin limctl -- list runs

# Генерация отчёта
cargo run --bin limctl -- report <run-id> --format html --output reports/latest.html
```

### MVP-1: Полнофункциональный стек (5 минут)

```bash
# 1. Запустить все сервисы (PostgreSQL + Ingest + Selenium)
docker compose -f deploy/docker-compose.mvp1.yml up -d

# 2. Запустить демо со встроенными данными
cd scripts && ./demo.sh

# 3. Сгенерировать HTML-отчёт
docker run --rm --network liminal \
  -e LIMINAL_PG_URL=postgres://liminal:liminal@pg:5432/liminal \
  liminal-report <run-id> /tmp/report.html
```

**📖 Полная инструкция**: [MVP-1 Quickstart](docs/MVP1_QUICKSTART.md)

## 📊 LIMINAL-DB

Би-темпоральное хранилище с индексами по времени:

```rust
// Entities (ULID)
System, Build, Run, Test, Artifact, Signal, Resonance

// Key attributes
:test/status       → pass|fail|xfail|flake
:test/duration     → milliseconds
:ui/screenshot     → sha256/path
:api/response      → sha256/chunkref
:ws/latency        → milliseconds
:resonance/pattern → flake pattern
:resonance/score   → 0.0..1.0

// Temporal axes
valid_time  — когда факт был истинен
tx_time     — когда мы о нём узнали
```

### Запросы

- **Timeshift**: "Как выглядела система 3 дня назад?"
- **Causality Walk**: "Что привело к этому падению?"
- **Resonance Map**: "Где система дрожит?"

## 🎬 Пример теста

```rust
use liminalqa_runner::*;

struct LoginTest;

impl TestCase for LoginTest {
    fn guidance(&self) -> Guidance {
        Guidance::new("User should be able to log in")
            .with_observable(Observable::UiVisible {
                selector: "#login-button"
            })
            .with_observable(Observable::ApiStatus {
                endpoint: "/api/auth/login",
                status: 200
            })
    }

    async fn execute(&self, navigator: &CoNavigator, council: &mut InnerCouncil) {
        // UI interaction
        council.record(ui_signal);

        // API call with retry
        navigator.execute_with_retry(api_call).await?;
        council.record(api_signal);
    }
}
```

## 📈 Дорожная карта

- ✅ **MVP-0**: REST-ingest, smoke-тесты, локальные артефакты
- ✅ **MVP-1**: LIMINAL-DB с двумя осями времени, Reflection v1 (HTML), Causality Walks
  - Bi-temporal PostgreSQL schema с `valid_time` × `tx_time`
  - REST API ingest service (Actix Web)
  - HTML reflection reports с causality trails
  - Docker Compose для быстрого старта
  - Демо-скрипт с примерами данных
- 🔜 **MVP-2**: gRPC-ingest, Resonance Map, baseline-детектор флейков
- 🔜 **MVP-3**: Nix/OCI, SBOM, интеграции (GHA/GitLab/Jenkins)

## 📚 Демонстрация возможностей

Для демонстрации возможностей системы создано демо-приложение `demo-app` и соответствующий тест-план `demo-app/liminal-test-plan.yaml`. Демо-приложение включает:

- Эндпоинты с искусственными задержками
- Эндпоинты с вероятностными ошибками (для демонстрации детекции флейков)
- Эндпоинты с различными типами ответов
- Сценарии с различными статусами ошибок

Также реализованы все основные CLI команды:
- `limctl run` — запуск тестов
- `limctl report` — генерация отчетов в различных форматах (HTML, JSON, Markdown)
- `limctl query` — выполнение би-временных запросов
- `limctl collect` — сбор артефактов
- `limctl init` — инициализация нового проекта
- `limctl import-cgqa` — строгая офлайн-проверка bounded evidence из ContractGraph-QA
- `limctl export-cgqa-candidates` — офлайн-экспорт неавторитетных candidate seeds
- `limctl cgqa-conformance` — 14 канонических взаимных golden/fail-closed vectors на Rust

## 🔗 Связанные проекты

- [LiminalOS](https://github.com/safal207/LiminalOSAI) — Герметичные прогоны
- [LIMINAL-DB](https://github.com/safal207/LiminalBD) — Би-темпоральная база

## 📝 API Endpoints

### Ingest Server (порт 8080)

```bash
# Health check
GET /health

# Ingest run
POST /ingest/run
{
  "run": {
    "id": "01HJQK...",
    "build_id": "01HJQJ...",
    "plan_name": "smoke",
    "env": {...},
    ...
  }
}

# Ingest tests
POST /ingest/tests
{
  "tests": [...]
}

# Ingest signals
POST /ingest/signals
{
  "signals": [...]
}

# Query
POST /query
{
  "valid_time_range": {...},
  "limit": 100
}
```

## 🎯 Позиционирование

**On-prem, безоблачная установка.**

Совместимость с любым CI.

Наблюдаемость "по умолчанию": тест → событие → резонанс → решение.

Анонимизированные паттерны резонанса — общая база знаний.

### Питч

> "Мы превращаем QA в систему памяти и причинности. Продукт получает пульс и карту резонансов, команда — меньше шума, больше истины."

## 📚 Документация

- **[Grant Evidence Package](docs/GRANT_EVIDENCE.md)** — reviewer-facing evidence matrix, product wedge, limitations, and roadmap
- **[MVP-1 Quickstart](docs/MVP1_QUICKSTART.md)** — начало работы за 5 минут
- **[Architecture](docs/ARCHITECTURE.md)** — подробная архитектура системы
- **[ContractGraph-QA Interop](docs/CGQA_INTEROP.md)** — взаимный evidence/candidate адаптер
- **[Quickstart (Development)](docs/QUICKSTART.md)** — локальная разработка
- **[Demo Guide](DEMO_GUIDE.md)** — руководство по демонстрации возможностей

## 🏢 Для корпораций

- **On-prem установка**: без облаков, полный контроль
- **Совместимость**: любой CI/CD (GitHub Actions, GitLab, Jenkins)
- **Безопасность**: маскирование секретов, хеширование артефактов
- **Масштабирование**: PostgreSQL + горизонтально масштабируемые ingest сервисы

## 🤝 Вклад

Проект находится в стадии активной разработки. Мы приветствуем контрибьюции!

## 📄 Лицензия

MIT

---

**Создано с 🧠 для превращения QA в систему осознанности**

## 📊 Monitoring

LiminalQA includes comprehensive monitoring with Prometheus and Grafana.

### Quick Start

```bash
# Start monitoring stack
cd deploy
docker-compose -f docker-compose.monitoring.yml up -d

# Access dashboards
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
```

### Available Metrics

- Test execution rate and success rate
- Test duration percentiles (p50, p95, p99)
- Active concurrent tests
- Resource usage (CPU, Memory)
- QA findings discovered

### Dashboards

- **Main Dashboard**: Overview of all test metrics
- **Performance**: Detailed latency analysis
- **System Health**: Resource usage and alerts

For detailed documentation, see [docs/monitoring/README.md](docs/monitoring/README.md).

### Alerts

Configured alerts for:
- Service downtime
- High error rates
- Slow test execution
- Resource exhaustion

See [docs/monitoring/alerts.md](docs/monitoring/alerts.md) for details.
