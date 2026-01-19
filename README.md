# 🚀 LiminalQA Engineer

<div align="center">

[![CI](https://github.com/safal207/LiminalQAengineer/workflows/CI/badge.svg)](https://github.com/safal207/LiminalQAengineer/actions)
[![codecov](https://codecov.io/gh/safal207/LiminalQAengineer/branch/main/graph/badge.svg)](https://codecov.io/gh/safal207/LiminalQAengineer)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Rust Version](https://img.shields.io/badge/rust-1.75%2B-orange.svg)](https://www.rust-lang.org)

_The Bi-Temporal QA Platform with a Soul_ ❤️

[Features](#-features) •
[Quick Start](#-quick-start) •
[Documentation](#-documentation) •
[Contributing](#-contributing) •
[Roadmap](#-roadmap)

</div>

---

## 💡 What is LiminalQA?

LiminalQA isn't just another test reporter. It's a **bi-temporal QA platform** that understands:

- **WHEN** it happened (valid_time)
- **WHEN** we discovered it (tx_time)
- **WHY** it happened (causality analysis)
- **WHAT** to do next (AI-powered guidance)

### 🌟 The LIMINAL Philosophy

```
Guidance → Co-Navigation → Inner Council → Reflection
```

Not just "test failed" — but "here's the story of what happened and how to fix it."

---

## ✨ Features

### 🔥 Core Capabilities

- **⚡ Batch Ingestion**: Ingest entire test runs in one API call (75% faster)
- **🔍 Test Lookup by Name**: No need to track IDs manually
- **🔒 Secure by Default**: Bearer token authentication
- **📊 Bi-Temporal Storage**: Time-travel through your test history
- **🎯 Causality Analysis**: Connect the dots between UI, API, and system signals
- **📈 Pattern Detection**: Find flaky tests and resonance patterns
- **🤖 AI-Ready**: Designed for ML-powered root cause analysis

### 🛠️ Developer Experience

- **REST API** with OpenAPI/Swagger docs
- **gRPC** support (coming soon)
- **CLI tools** for local development
- **Docker** support for easy deployment
- **Prometheus** metrics out of the box

---

## 🚀 Quick Start

### Prerequisites

- Rust 1.75+
- Docker (optional)

### Installation

```bash
# Clone the repository
git clone https://github.com/safal207/LiminalQAengineer.git
cd LiminalQAengineer

# Build the project
cargo build --release

# Run the ingest server
LIMINAL_AUTH_TOKEN=your-secret-token \
  ./target/release/liminalqa-ingest
```

### Docker (Recommended)

```bash
# Using docker-compose
docker-compose up -d

# The API will be available at http://localhost:8080
```

### Your First API Call

```bash
export TOKEN=your-secret-token

# Ingest a complete test run
curl -X POST http://localhost:8080/ingest/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "run": {
      "run_id": "01HX001",
      "build_id": "01HX000",
      "plan_name": "smoke_tests",
      "env": {},
      "started_at": "2026-01-20T10:00:00Z"
    },
    "tests": [{
      "name": "test_login",
      "suite": "auth",
      "status": "pass",
      "duration_ms": 150
    }],
    "signals": [{
      "test_name": "test_login",
      "kind": "api",
      "latency_ms": 45,
      "at": "2026-01-20T10:00:01Z"
    }]
  }'
```

---

## 📚 Documentation

- [API Reference](docs/api.md)
- [Architecture Guide](docs/architecture.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Developer Setup](docs/development.md)

---

## 🏗️ Architecture

```
┌─────────────────┐
│  Test Runners   │
│ (pytest, jest)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Ingest API     │
│  (REST/gRPC)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LiminalDB     │
│ (Bi-Temporal)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Query Engine   │
│ (Coming Soon)   │
└─────────────────┘
```

---

## 🗺️ Roadmap

### ✅ Q1 2026 (Current)
- [x] Bearer Authentication
- [x] DTO Layer
- [x] Test Lookup by Name
- [x] Batch Ingestion API
- [x] CI/CD Pipeline
- [ ] 80% Test Coverage
- [ ] gRPC Endpoint

### 🎯 Q2 2026
- [ ] Query API v1
- [ ] Auto-Triage
- [ ] Resonance Detection
- [ ] Web Dashboard
- [ ] Slack Integration

### 🔮 Q3 2026
- [ ] Predictive Flake Detection
- [ ] Statistical Baselines
- [ ] ML-Powered Root Cause
- [ ] Test Impact Analysis

### 🚀 Q4 2026
- [ ] Pattern Sharing Registry
- [ ] Enterprise Features
- [ ] SaaS Beta
- [ ] Liminal OS

[View full roadmap](ROADMAP.md)

---

## 🤝 Contributing

We ❤️ contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Steps

```bash
# 1. Fork & clone
git clone https://github.com/YOUR_USERNAME/LiminalQAengineer.git

# 2. Create a branch
git checkout -b feature/amazing-feature

# 3. Make changes and test
cargo test --workspace
cargo clippy --fix
cargo fmt

# 4. Commit using conventional commits
git commit -m "feat(api): add amazing feature"

# 5. Push and create PR
git push origin feature/amazing-feature
```

### Contributors ✨

Thanks to these wonderful people:

<!-- ALL-CONTRIBUTORS-LIST:START -->
<table>
  <tr>
    <td align="center">
      <a href="https://github.com/safal207">
        <img src="https://github.com/safal207.png" width="100px;" alt=""/>
        <br /><sub><b>Safal</b></sub>
      </a>
      <br />💻 🎨 📖
    </td>
    <td align="center">
      <a href="https://github.com/google-labs-jules">
        <img src="https://github.com/google-labs-jules.png" width="100px;" alt=""/>
        <br /><sub><b>Jules (Bot)</b></sub>
      </a>
      <br />🤖 💻
    </td>
    <!-- Add more contributors here -->
  </tr>
</table>
<!-- ALL-CONTRIBUTORS-LIST:END -->

---

## 📊 Stats

<div align="center">

![GitHub Stars](https://img.shields.io/github/stars/safal207/LiminalQAengineer?style=social)
![GitHub Forks](https://img.shields.io/github/forks/safal207/LiminalQAengineer?style=social)
![GitHub Issues](https://img.shields.io/github/issues/safal207/LiminalQAengineer)
![GitHub Pull Requests](https://img.shields.io/github/issues-pr/safal207/LiminalQAengineer)

</div>

---

## 🙏 Acknowledgments

Built with ❤️ using:
- [Rust](https://www.rust-lang.org/) - The language of choice
- [Axum](https://github.com/tokio-rs/axum) - Web framework
- [Sled](https://github.com/spacejam/sled) - Embedded database
- [Tokio](https://tokio.rs/) - Async runtime

Special thanks to:
- The Rust community for amazing tools
- Early adopters for feedback
- Contributors for making this better

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 💬 Community

- 🐛 [Report a Bug](https://github.com/safal207/LiminalQAengineer/issues/new?template=bug_report.yml)
- ✨ [Request a Feature](https://github.com/safal207/LiminalQAengineer/issues/new?template=feature_request.yml)
- 💬 [Join Discussions](https://github.com/safal207/LiminalQAengineer/discussions)
- 📧 Email: liminalqa@example.com

---

<div align="center">

**[⬆ back to top](#-liminalqa-engineer)**

Made with 💖 by the LiminalQA community

_"Testing is an art. We provide the canvas."_ 🎨

</div>
