# 📖 Changelog

All notable changes to LiminalQA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 🎯 Planned
- gRPC ingestion endpoint
- Query engine with temporal filtering
- Web dashboard
- ML-powered root cause analysis

## [0.1.0] - 2026-01-20

### ✨ Added
- **Batch Ingestion API**: Single endpoint for run + tests + signals + artifacts
- **Test Lookup by Name**: Resolve test_id from test_name
- **Bearer Authentication**: Secure API with token-based auth
- **DTO Layer**: Clean API schema separate from internal models
- **Integration Tests**: Full test coverage for critical paths
- **CI/CD Pipeline**: Automated testing, linting, and builds

### 🐛 Fixed
- Removed all `.unwrap()` calls in production code
- Fixed race conditions in test lookup
- Improved error messages for better debugging

### ⚡ Performance
- Batch API reduces network calls by 75%
- Optimized database indexing for faster lookups
- Added caching for test name resolution

### 🔒 Security
- Mandatory authentication for all endpoints
- Security audit in CI pipeline
- Input validation on all endpoints

### 📚 Documentation
- API documentation with OpenAPI/Swagger
- Developer contribution guide
- Architecture documentation

## [0.0.1] - 2026-01-01

### ✨ Initial Release
- Basic ingestion endpoints (run, tests, signals, artifacts)
- sled-based storage engine
- Bi-temporal data model
- Command-line tools (limctl)

---

[Unreleased]: https://github.com/safal207/LiminalQAengineer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/safal207/LiminalQAengineer/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/safal207/LiminalQAengineer/releases/tag/v0.0.1
