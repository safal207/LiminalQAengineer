# 🤝 Contributing to LiminalQA

Thank you for your interest in contributing to LiminalQA! ❤️

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Review Process](#review-process)

## 📜 Code of Conduct

Be respectful, inclusive, and professional. We're all here to build something great together.

## 🚀 Getting Started

### Prerequisites

- Rust 1.75 or later
- Git
- Familiarity with Rust and async programming

### Setup

```bash
# Clone the repository
git clone https://github.com/safal207/LiminalQAengineer.git
cd LiminalQAengineer

# Build the project
cargo build

# Run tests
cargo test

# Run the CLI
cargo run --bin limctl -- --help
```

## 🔄 Development Workflow

### 1. Create a Branch

```bash
# For new features
git checkout -b feature/your-feature-name

# For bug fixes
git checkout -b fix/issue-description

# For documentation
git checkout -b docs/what-youre-documenting
```

### 2. Make Changes

- Write clear, concise code
- Add tests for new functionality
- Update documentation as needed
- Follow the style guide (see below)

### 3. Test Your Changes

```bash
# Run all tests
cargo test --workspace

# Run tests for specific package
cargo test -p liminalqa-core

# Run with all features
cargo test --all-features

# Check formatting
cargo fmt --all -- --check

# Run clippy
cargo clippy --all-targets --all-features -- -D warnings
```

### 4. Commit Your Changes

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
# Feature
git commit -m "feat: add support for parallel test execution"

# Bug fix
git commit -m "fix: resolve race condition in test runner"

# Documentation
git commit -m "docs: add examples for CLI usage"

# Breaking change
git commit -m "feat!: redesign configuration format

BREAKING CHANGE: Configuration now uses TOML instead of JSON"
```

**Commit Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

## 🎨 Code Style

### Rust Style

- Follow the [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- Use `cargo fmt` for formatting
- Address all `cargo clippy` warnings
- Maximum line length: 100 characters

### Error Handling

```rust
// ❌ Bad
let data = file.read().unwrap();

// ✅ Good
let data = file.read()
    .map_err(|e| Error::FileRead { path: file_path, source: e })?;

// ✅ Also good (when failure is truly impossible)
let data = file.read()
    .expect("config file must exist at this point due to validation");
```

### Documentation

```rust
/// Runs a test suite and collects results.
///
/// # Arguments
///
/// * `suite` - The test suite to execute
/// * `config` - Runtime configuration options
///
/// # Returns
///
/// Returns a `TestResult` containing execution statistics and findings.
///
/// # Errors
///
/// Returns `Error::TestExecutionFailed` if any test in the suite fails
/// to execute due to runtime errors (not test failures).
///
/// # Examples
///
/// ```
/// use liminalqa_runner::{Runner, TestSuite};
///
/// let suite = TestSuite::from_file("tests.yaml")?;
/// let result = Runner::new().run_suite(&suite).await?;
/// println!("Tests passed: {}", result.passed_count);
/// ```
pub async fn run_suite(&self, suite: &TestSuite) -> Result<TestResult> {
    // Implementation
}
```

## 🧪 Testing

### Test Organization

```
tests/
├── unit/           # Unit tests (also in src/ modules)
├── integration/    # Integration tests
└── fixtures/       # Test data and fixtures
```

### Writing Tests

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_functionality() {
        let result = do_something();
        assert_eq!(result, expected);
    }

    #[tokio::test]
    async fn test_async_operation() {
        let result = async_operation().await.unwrap();
        assert!(result.is_valid());
    }

    #[test]
    #[should_panic(expected = "invalid input")]
    fn test_error_handling() {
        process_invalid_input();
    }
}
```

### Test Coverage

- Aim for >80% code coverage on new code
- All public APIs must have tests
- Critical paths must have integration tests

## 📤 Submitting Changes

### Before Submitting

Run the pre-submit checklist:

```bash
# Format code
cargo fmt --all

# Run clippy
cargo clippy --all-targets --all-features -- -D warnings

# Run all tests
cargo test --workspace --all-features

# Check documentation
cargo doc --no-deps --workspace

# Build in release mode
cargo build --release
```

### Creating a Pull Request

1. Push your branch to GitHub
2. Open a Pull Request against `main`
3. Fill out the PR template completely
4. Link related issues
5. Request review from maintainers

### PR Requirements

- ✅ All CI checks must pass
- ✅ Code review approval required
- ✅ No merge conflicts
- ✅ Tests added for new functionality
- ✅ Documentation updated
- ✅ CHANGELOG.md updated (for user-facing changes)

## 👀 Review Process

### What to Expect

- Initial review within 2-3 business days
- Constructive feedback on code and design
- Possible requests for changes
- Approval and merge once all requirements met

### Addressing Feedback

```bash
# Make requested changes
git add .
git commit -m "refactor: address review feedback"
git push
```

The PR will automatically update. No need to close and reopen.

## 🏗️ Project Structure

```
LiminalQAengineer/
├── limctl/              # CLI tool
├── liminalqa-core/      # Core types and traits
├── liminalqa-db/        # Database layer
├── liminalqa-runner/    # Test execution engine
└── liminalqa-ingest/    # Data ingestion service (future)
```

## 📚 Additional Resources

- [Rust Book](https://doc.rust-lang.org/book/)
- [Async Rust](https://rust-lang.github.io/async-book/)
- [Project Documentation](https://docs.rs/liminalqa)
- [Issue Tracker](https://github.com/safal207/LiminalQAengineer/issues)

## 🆘 Getting Help

- Open an issue for bugs
- Start a discussion for questions
- Join our community chat (link)

## 🎉 Recognition

Contributors are recognized in:
- CHANGELOG.md for their contributions
- GitHub contributors page
- Release notes

Thank you for contributing! 🙌

---

_Made with ❤️ by the LiminalQA community_
