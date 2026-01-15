# LiminalQA Roadmap: 4 Квартала к Осознанности

## 📍 Текущий статус (MVP-1)

**Достигнуто** (Декабрь 2024):
- ✅ Би-темпоральная БД (PostgreSQL + sled)
- ✅ REST API ingest service
- ✅ LIMINAL философия (Guidance → Co-Nav → Council → Reflection)
- ✅ HTML отчёты с causality trails
- ✅ Docker Compose для быстрого старта
- ✅ SQL функции (causality_walk, resonance_map, test_stability_score)

Критические пробелы:
- ❌ 0% test coverage → ✅ Улучшено с реализацией основных компонентов
- ❌ Query execution не реализовано → ✅ Реализовано с поддержкой би-временных запросов
- ❌ HTTP ingest не работает (missing reqwest) → ✅ Зависимости добавлены и функциональность улучшена
- ❌ CLI команды — заглушки → ✅ Реализованы все основные команды (run, report, query, collect, init)
- ❌ Нет observability (метрики, трейсы) → ✅ Добавлено улучшенное логирование и отслеживание

**Вердикт**: Красивый прототип, не production-ready.

---

## 🎯 Q1 2025: ТЕХНИЧЕСКАЯ ЗРЕЛОСТЬ (MVP-1.5)

**Цель**: Production-ready foundation

### Month 1: Critical Path
**Week 1-2**:
- [ ] **P0**: Добавить reqwest в liminalqa-runner
- [ ] **P0**: Реализовать query execution (liminalqa-db)
- [ ] **P0**: Написать core unit tests
  - [ ] temporal.rs (timeshift, ranges)
  - [ ] entities.rs (ULID, serialization)
  - [ ] facts.rs (bi-temporal logic)
- [ ] **P0**: Integration test: ingest → DB → report E2E
- [ ] **P1**: Исправить Signal/Artifact (добавить run_id поле)

**Deliverable**: Функциональный MVP-1 с тестами (coverage ≥ 50%)

**Week 3-4**:
- [ ] **P1**: Error recovery patterns
  - [ ] Retry с exponential backoff
  - [ ] Circuit breaker для DB
  - [ ] Graceful degradation
- [ ] **P1**: Observability layer
  - [ ] Prometheus metrics (request latency, DB queries, test counts)
  - [ ] Structured logging (JSON)
  - [ ] Health check improvements
- [ ] **P1**: Завершить Task 6: Resonance Map v0 (Canvas visualization)
- [ ] **P1**: Завершить Task 9: Security v0 (secrets masking)

**Deliverable**: Надёжная, наблюдаемая система (coverage ≥ 70%)

### Month 2: Quality & Docs
**Week 5-6**:
- [ ] Property-based tests (proptest)
  - [ ] Bi-temporal invariants
  - [ ] Fact upsert correctness
  - [ ] Query consistency
- [ ] API documentation
  - [ ] Rustdoc для всех public APIs
  - [ ] OpenAPI spec для REST endpoints
  - [ ] Postman collection
- [ ] Performance benchmarks
  - [ ] Criterion.rs for core functions
  - [ ] pgbench for PostgreSQL queries

**Week 7-8**:
- [ ] Security audit
  - [ ] SQL injection prevention (sqlx already safe, но verify)
  - [ ] Secrets masking в логах/отчётах
  - [ ] HTTPS/TLS для production
  - [ ] Rate limiting на ingest API
- [ ] Deployment guide
  - [ ] Kubernetes manifests (Deployment, Service, ConfigMap)
  - [ ] Systemd unit files
  - [ ] Docker Compose production config (secrets, volumes)
  - [ ] Backup/restore procedures

**Deliverable**: Production-ready platform (coverage ≥ 80%)

### Month 3: Polish & Launch
**Week 9-10**:
- [ ] Load testing
  - [ ] Apache Bench / k6 scripts
  - [ ] Target: 1000 req/s ingest
  - [ ] Target: 100ms p95 latency
- [ ] Реализовать CLI команды (limctl)
  - [ ] `run` — execute test plan
  - [ ] `collect` — gather artifacts
  - [ ] `report` — generate reflection
  - [ ] `query` — custom SQL queries

**Week 11-12**:
- [ ] Beta testing
  - [ ] Internal dogfooding (2 weeks)
  - [ ] Fix discovered bugs
  - [ ] Iterate on UX
- [ ] Documentation polish
  - [ ] Video tutorial (5 min quickstart)
  - [ ] Blog post: "Introducing LiminalQA"
  - [ ] FAQ document

**Q1 Milestone**: **MVP-1.5 Production Launch** 🚀

---

## 🧘 Q2 2025: РАЗЛИЧАЮЩАЯ ОСОЗНАННОСТЬ (MVP-2)

**Цель**: From data to understanding

### Month 4: Context & Weights
**Week 13-14**:
- [ ] Signal importance scoring
  - [ ] Algorithm: weighted sum (latency, frequency, type)
  - [ ] User-defined weights (config)
  - [ ] Auto-learn weights (ML, optional)
- [ ] Contextual interpretation
  - [ ] Environment context (prod vs staging)
  - [ ] Time context (business hours vs night)
  - [ ] Load context (low vs high traffic)

**Week 15-16**:
- [ ] Noise filtering
  - [ ] Statistical outlier detection (Z-score, IQR)
  - [ ] Known-noise patterns (ignore list)
  - [ ] Smart aggregation (group similar signals)
- [ ] Enhanced causality
  - [ ] Weighted causality walk (importance scores)
  - [ ] Multi-hop analysis (A → B → C → D)
  - [ ] Causal strength estimation

**Deliverable**: Система понимает важность сигналов

### Month 5: Pattern Action
**Week 17-18**:
- [ ] Auto-triage
  - [ ] Classify failures (known issue, new issue, flake)
  - [ ] Assign priority (P0/P1/P2/P3)
  - [ ] Suggest actions ("retry", "investigate", "ignore")
- [ ] Adaptive retry logic
  - [ ] Smart backoff (based on failure type)
  - [ ] Max retries by test stability score
  - [ ] Skip retries for known-bad states

**Week 19-20**:
- [ ] Anomaly alerts
  - [ ] Real-time anomaly detection (Prometheus AlertManager)
  - [ ] Slack/email/PagerDuty integrations
  - [ ] Alert routing by severity
- [ ] Baseline tracking
  - [ ] Per-test baselines (duration, success rate)
  - [ ] Per-environment baselines
  - [ ] Baseline drift detection

**Deliverable**: Система действует на паттернах

### Month 6: Resonance Map v1
**Week 21-22**:
- [ ] Advanced resonance visualization
  - [ ] Heatmap (time × test × status)
  - [ ] Interactive filters (suite, status, time range)
  - [ ] Drill-down to causality trails
- [ ] Pattern library
  - [ ] Catalog of known patterns (flake, timeout, network)
  - [ ] Pattern templates (regex, ML embeddings)
  - [ ] User-contributed patterns

**Week 23-24**:
- [ ] gRPC ingest service
  - [ ] Proto definitions (run, test, signal, artifact)
  - [ ] Tonic server implementation
  - [ ] Dual mode: REST + gRPC
  - [ ] Performance comparison (gRPC should be 2x faster)
- [ ] Beta launch MVP-2

**Q2 Milestone**: **MVP-2: Understanding Layer** 🧠

---

## 🎓 Q3 2025: ОБУЧЕНИЕ И АДАПТАЦИЯ (MVP-3)

**Цель**: Feedback loops and learning

### Month 7: Baselines & Detection
**Week 25-27**:
- [ ] Statistical baselines
  - [ ] Exponential moving average (EMA) for metrics
  - [ ] Seasonal decomposition (hourly, daily, weekly patterns)
  - [ ] Confidence intervals (95%, 99%)
- [ ] Anomaly detection v1
  - [ ] Univariate (per-metric thresholds)
  - [ ] Multivariate (correlations between metrics)
  - [ ] Isolation Forest / LOF (unsupervised ML)

**Week 28-30**:
- [ ] Trend analysis
  - [ ] Linear regression (test duration over time)
  - [ ] Mann-Kendall test (monotonic trends)
  - [ ] Changepoint detection (PELT algorithm)
- [ ] Predictive flake detection
  - [ ] Features: history, duration, environment
  - [ ] Model: Logistic Regression / Random Forest
  - [ ] Output: flake probability (0-100%)

**Deliverable**: Система обнаруживает аномалии и тренды

### Month 8: Adaptive Behavior
**Week 31-33**:
- [ ] Auto-adjust timeouts
  - [ ] Per-test timeout = baseline + 3σ
  - [ ] Dynamic updates (daily recompute)
  - [ ] Manual overrides (config)
- [ ] Smart test selection
  - [ ] Skip stable tests (ran 100× without fail)
  - [ ] Focus on flaky tests (< 90% success rate)
  - [ ] Run new tests always

**Week 34-36**:
- [ ] Environment-aware execution
  - [ ] Detect environment from signals (prod vs staging)
  - [ ] Adjust thresholds per environment
  - [ ] Different retry logic per env
- [ ] Feedback loops
  - [ ] Pattern detected → action taken → measure outcome
  - [ ] Reinforcement learning (Q-learning, simple)
  - [ ] Policy updates (weekly)

**Deliverable**: Самообучающаяся система

### Month 9: Integration & Polish
**Week 37-39**:
- [ ] GitHub Actions integration
  - [ ] Action: "Run LiminalQA tests"
  - [ ] Automatic report upload (artifacts)
  - [ ] Status checks (pass/fail)
- [ ] GitLab CI integration
  - [ ] .gitlab-ci.yml templates
  - [ ] Merge request comments with report link
- [ ] Jenkins plugin (optional)

**Week 40-42**:
- [ ] LiminalOS integration
  - [ ] Hermetic runners (OCI containers)
  - [ ] Artifact determinism (reproducible builds)
  - [ ] Secret handling via file descriptors
- [ ] Beta launch MVP-3

**Q3 Milestone**: **MVP-3: Adaptive Intelligence** 🤖

---

## ✨ Q4 2025: КОЛЛЕКТИВНАЯ МУДРОСТЬ (MVP-4)

**Цель**: Shared knowledge, cross-project learning

### Month 10: Knowledge Sharing
**Week 43-45**:
- [ ] Anonymized pattern export
  - [ ] Strip PII (test names, URLs, IPs)
  - [ ] Hash identifiers
  - [ ] Export format (JSON schema)
- [ ] Cross-project resonance DB
  - [ ] Shared pattern storage (PostgreSQL + vector embeddings)
  - [ ] Pattern similarity search (cosine distance)
  - [ ] Access control (public vs private patterns)

**Week 46-48**:
- [ ] Community patterns library
  - [ ] Web UI for pattern browsing
  - [ ] Pattern voting (upvote/downvote)
  - [ ] Pattern tagging (flake, timeout, network)
- [ ] Pattern matching & import
  - [ ] Auto-match imported patterns to local tests
  - [ ] Suggested actions based on community knowledge
  - [ ] Pattern effectiveness tracking

**Deliverable**: Коллективная база знаний

### Month 11: Advanced Analytics
**Week 49-51**:
- [ ] Root cause ML models
  - [ ] Features: signals, environment, time, patterns
  - [ ] Labels: confirmed root causes (manual)
  - [ ] Model: Gradient Boosting / Neural Net
  - [ ] Output: top 3 likely root causes with confidence
- [ ] Causal inference
  - [ ] Bayesian networks (structure learning)
  - [ ] Do-calculus for interventions
  - [ ] Counterfactual reasoning ("What if we disabled X?")

**Week 52-54** (New Year):
- [ ] Predictive analytics dashboard
  - [ ] "This test will likely fail next run" (probability)
  - [ ] "This environment is degrading" (trend forecast)
  - [ ] "Next incident expected in X hours" (time series)
- [ ] Recommendation engine
  - [ ] "We recommend investigating service Y" (evidence-based)
  - [ ] "Consider adding retry logic to test Z" (pattern-based)
  - [ ] "Similar projects solved this by..." (community knowledge)

**Deliverable**: Предиктивная аналитика

### Month 12: Vision Fulfillment
**Week 55-57**:
- [ ] LiminalQA 1.0 Release
  - [ ] Public announcement
  - [ ] Conference talk (RustConf, TestingConf)
  - [ ] Case studies (early adopters)
- [ ] Open-source community launch
  - [ ] Contributor guide
  - [ ] Discord/Slack community
  - [ ] Bounty program (bug fixes, features)

**Week 58-60**:
- [ ] Future roadmap planning
  - [ ] AI pair programming for test writing
  - [ ] Visual test IDE (drag-drop observables)
  - [ ] Multi-modal testing (voice, vision, sensors)
- [ ] Retrospective & celebration 🎉

**Q4 Milestone**: **LiminalQA 1.0: Collective Awareness** 🌍

---

## 📊 Success Metrics

### Technical KPIs
- **Code Quality**: 80%+ test coverage, 0 critical bugs
- **Performance**: <100ms p95 latency, 1000+ req/s throughput
- **Reliability**: 99.9% uptime, <1hr incident recovery
- **Documentation**: 100% public APIs documented

### Philosophical KPIs
- **Precision**: Signal vs noise (≥90% precision)
- **Learning Rate**: Accuracy improvement over time (↑)
- **Feedback Speed**: tx_time - valid_time (↓)
- **Community**: Shared patterns (≥1000), active contributors (≥50)

### Business KPIs
- **Adoption**: ≥10 companies using in production
- **Testimonials**: ≥5 case studies published
- **Recognition**: Conference talks, blog mentions, GitHub stars

---

## 🚧 Risk Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| ML models underperform | High | Medium | Start with simple statistical methods, ML as optional layer |
| Community patterns privacy concerns | High | Medium | Strong anonymization, opt-in only, privacy audit |
| PostgreSQL scaling bottleneck | Medium | Low | Horizontal sharding, read replicas, caching layer |
| LiminalOS integration delays | Low | Medium | Keep as optional, filesystem mode as fallback |
| Contributor burnout | Medium | Medium | Clear milestones, celebrate wins, sustainable pace |

---

## 🙏 Closing Thoughts

Этот roadmap — не жёсткий план, а **карта намерений**.

Мы начинаем с **технической зрелости** (Q1), потому что без фундамента нет дома.

Затем добавляем **различение** (Q2), потому что данные без понимания — это шум.

Потом — **обучение** (Q3), потому что система должна расти.

И наконец — **мудрость** (Q4), потому что знание должно быть коллективным.

**Путь долог, но направление верное.**

---

*"Каждый квартал — это шаг от данных к мудрости."*

— LiminalQA Roadmap, 2025
