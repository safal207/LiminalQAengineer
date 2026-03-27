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
- [x] Statistical baselines
  - [x] Exponential moving average (EMA) for metrics (`baseline::ExponentialBaseline`)
  - [ ] Seasonal decomposition (hourly, daily, weekly patterns)
  - [x] Confidence intervals — EMA confidence grows 0→1 as samples accumulate
- [x] Anomaly detection v1
  - [x] Univariate (per-metric thresholds via EMA mean ± kσ)
  - [ ] Multivariate (correlations between metrics)
  - [ ] Isolation Forest / LOF (unsupervised ML)

**Week 28-30**:
- [x] Trend analysis
  - [x] Linear regression on test duration over time (`baseline::TrendStats`)
  - [x] Monotonic trend detection (slope sign + significance threshold)
  - [ ] Changepoint detection (PELT algorithm)
- [x] Predictive flake detection
  - [x] Features: history, duration trend, environment (`baseline::FlakeRiskScore`)
  - [x] Logistic-regression-style scoring with configurable weights
  - [x] Output: flake probability (0–100%)

**Deliverable**: ✅ Система обнаруживает аномалии и тренды

### Month 8: Adaptive Behavior
**Week 31-33**:
- [x] Auto-adjust timeouts
  - [x] Per-test timeout = EMA mean + 3σ (`retry::AdaptiveTimeout`)
  - [x] Dynamic updates on every run
  - [x] Manual cap override via `max_timeout_ms`
- [x] Smart test selection
  - [x] Skip stable tests (≥97% pass rate over ≥10 runs)
  - [x] Always run flaky / new tests (`retry::SmartSelector`)

**Week 34-36**:
- [x] Environment-aware execution
  - [x] Env class from `export::EnvClass` (prod/staging/dev/ci)
  - [x] Context multiplier adjusts thresholds per env (`context::SignalContext`)
- [x] Feedback loops (foundation)
  - [x] Pattern detected → action recorded → outcome updates weights
  - [x] Online Bayesian weight update in `rootcause::RootCauseEngine`

**Deliverable**: ✅ Самообучающаяся система

### Month 9: Integration & Polish
**Week 37-39**:
- [x] GitHub Actions integration
  - [x] Workflow template: ingest results + status check
  - [x] Report upload as artifact
- [x] GitLab CI integration
  - [x] `.gitlab-ci.yml` template with MR comment support
- [ ] Jenkins plugin (optional, deferred)

**Week 40-42**:
- [x] Agent-facing decision layer (`decision::TestDecision`, `SuiteDecision`)
  - [x] Merge policy (block / allow / allow_with_warning)
  - [x] Structured JSON for OpenAI/Anthropic tool calling
  - [x] `limctl decision <suite>/<test>` CLI support
- [ ] LiminalOS hermetic runners (deferred to post-1.0)
- [ ] Beta launch MVP-3 (in progress)

**Q3 Milestone**: **MVP-3: Adaptive Intelligence** ✅ (core complete)

---

## ✨ Q4 2025: КОЛЛЕКТИВНАЯ МУДРОСТЬ (MVP-4)

**Цель**: Shared knowledge, cross-project learning

### Month 10: Knowledge Sharing
**Week 43-45**:
- [x] Anonymized pattern export (`export::ExportBuilder`, `Anonymizer`)
  - [x] Strip PII: IPs, URLs, file paths replaced with `<ip>/<url>/<path>`
  - [x] Hash identifiers: SHA-256(salt ‖ name) → 16-char token
  - [x] Export format: versioned JSON bundle (`PatternExportBundle`)
- [x] Cross-project resonance DB (`community::PatternStore`)
  - [x] In-memory store with cosine-similarity nearest-neighbour search
  - [x] Near-duplicate deduplication (similarity ≥ 0.95 → increment count)
  - [ ] PostgreSQL + pgvector backend (deferred)
  - [ ] Access control (public vs private patterns — deferred)

**Week 46-48**:
- [x] Pattern matching & import
  - [x] `PatternStore::import_bundle` — bulk import from export bundle
  - [x] `PatternStore::find_similar` — top-K cosine matches with threshold
  - [x] `community::generate_suggestions` — actionable advice from matches
  - [x] `PatternStore::record_feedback` — Bayesian effectiveness tracking
- [ ] Web UI for community pattern browsing (deferred to post-MVP)
- [ ] Pattern voting UI (deferred)

**Deliverable**: ✅ Коллективная база знаний (core engine complete)

### Month 11: Advanced Analytics
**Week 49-51**:
- [x] Root cause analysis engine (`rootcause::RootCauseEngine`)
  - [x] Features: triage verdict, flake probability, trend slope, env class, community matches
  - [x] 6 hypothesis kinds: InfrastructureFlake / CodeRegression / TestDesignFlaw / ExternalDependency / ResourceExhaustion / EnvironmentConfig
  - [x] Top-3 hypotheses ranked by weighted evidence score + normalized confidence
  - [x] Online Bayesian weight update via `record_outcome` (learning rate 1/√n)
- [x] Counterfactual reasoning
  - [x] `what_if_fixed(result, kind)` → predicted success prob after intervention
  - [x] Per-hypothesis `counterfactual_success_prob` field
  - [ ] Full do-calculus / Bayesian network structure learning (deferred)

**Week 52-54** (New Year):
- [ ] Predictive analytics dashboard
  - [x] "This test will likely fail next run" — `FlakeRiskScore.flake_probability`
  - [x] "This environment is degrading" — `TrendStats.slope` with significance
  - [ ] Dashboard UI (deferred)
- [x] Recommendation engine (foundation)
  - [x] Evidence-based fix suggestions in `RootCauseHypothesis.suggested_fix`
  - [x] Community-knowledge suggestions via `generate_suggestions`
  - [ ] "Similar projects solved this by..." — requires community DB population

**Deliverable**: ✅ Предиктивная аналитика (core engine complete)

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
