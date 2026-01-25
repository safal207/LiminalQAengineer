# LiminalQA Engineer

[![CI](https://github.com/safal207/LiminalQAengineer/workflows/CI/badge.svg)](https://github.com/safal207/LiminalQAengineer/actions/workflows/ci.yml)
[![Security Audit](https://github.com/safal207/LiminalQAengineer/workflows/Security%20Audit/badge.svg)](https://github.com/safal207/LiminalQAengineer/actions/workflows/security-audit.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Миссия**: Превратить QA из набора ассёртов в систему коллективной осознанности продуктов.

**Опора**: Rust-движок тестов + собственные LIMINAL-DB (би-темпоральная) и LiminalOS (герметичные прогоны).

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

- **[MVP-1 Quickstart](docs/MVP1_QUICKSTART.md)** — начало работы за 5 минут
- **[Architecture](docs/ARCHITECTURE.md)** — подробная архитектура системы
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
