# 🤝 Contributing to LiminalQA

> _First off, thank you for considering contributing to LiminalQA! ❤️_

## 💖 Code of Conduct

We believe in kindness, respect, and collaboration. Be awesome to each other! 🌟

## 🚀 Quick Start

### 1. Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/LiminalQAengineer.git
cd LiminalQAengineer
```

### 2. Setup Development Environment

```bash
# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install development tools
cargo install cargo-tarpaulin  # Code coverage
cargo install cargo-audit      # Security auditing
cargo install cargo-watch      # Auto-rebuild on changes

# Run tests to verify setup
cargo test --workspace
```

### 3. Create a Branch

```bash
git checkout -b feature/amazing-feature
# or
git checkout -b fix/bug-description
```

## 🎨 Development Workflow

### Running the Project

```bash
# Start the ingest server
cd liminalqa-ingest
LIMINAL_AUTH_TOKEN=test123 cargo run

# In another terminal, run tests
cargo test --workspace

# Watch mode (auto-rebuild on changes)
cargo watch -x test
```

### Before Committing

```bash
# Run all quality checks
cargo fmt --all              # Format code
cargo clippy --fix           # Fix clippy warnings
cargo test --workspace       # Run all tests
cargo doc --no-deps          # Build documentation
```

### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): brief description

Longer description if needed.

Fixes #123
```

**Types:**
- ✨ `feat`: New feature
- 🐛 `fix`: Bug fix
- 📚 `docs`: Documentation changes
- 🎨 `style`: Code style changes (formatting, etc.)
- ♻️ `refactor`: Code refactoring
- ⚡ `perf`: Performance improvements
- 🧪 `test`: Adding/updating tests
- 🔧 `chore`: Maintenance tasks

**Examples:**
```
feat(ingest): add batch ingestion endpoint
fix(db): resolve race condition in test lookup
docs(readme): update installation instructions
```

## 🧪 Testing Guidelines

### Writing Tests

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_something_awesome() {
        // Arrange
        let input = "test data";

        // Act
        let result = awesome_function(input);

        // Assert
        assert_eq!(result, expected_output);
    }

    #[tokio::test]
    async fn test_async_operation() {
        // For async tests
        let result = async_function().await;
        assert!(result.is_ok());
    }
}
```

### Test Coverage

We aim for **80%+ code coverage**. Check coverage with:

```bash
cargo tarpaulin --workspace --out Html
# Open coverage/index.html in browser
```

## 🎯 Code Quality Standards

### No Panics in Production

❌ **Bad:**
```rust
let value = map.get(key).unwrap();  // Can panic!
```

✅ **Good:**
```rust
let value = match map.get(key) {
    Some(v) => v,
    None => return Err(Error::KeyNotFound),
};
```

### Meaningful Error Messages

❌ **Bad:**
```rust
return Err(anyhow!("error"));
```

✅ **Good:**
```rust
return Err(anyhow!("Failed to parse test name '{}': invalid format", name));
```

### Documentation

All public APIs must have doc comments:

```rust
/// Finds a test by name within a specific run.
///
/// # Arguments
/// * `run_id` - The run to search within
/// * `test_name` - The name of the test
///
/// # Returns
/// * `Ok(Some(test_id))` - Test found
/// * `Ok(None)` - Test not found
/// * `Err(_)` - Database error
///
/// # Examples
/// ```
/// let test_id = db.find_test_by_name(run_id, "test_login")?;
/// ```
pub fn find_test_by_name(&self, run_id: EntityId, test_name: &str) -> Result<Option<EntityId>> {
    // Implementation...
}
```

## 🔍 Pull Request Process

1. **Ensure CI passes** ✅
   - All tests must pass
   - No clippy warnings
   - Code must be formatted

2. **Update documentation** 📚
   - Update README if adding features
   - Add doc comments to new code
   - Update CHANGELOG.md

3. **Request review** 👀
   - Tag relevant reviewers
   - Be responsive to feedback
   - Make requested changes

4. **Celebrate!** 🎉
   - Your PR is merged!
   - You're awesome! ❤️

## 🐛 Reporting Bugs

Use our [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml) and include:
- Clear description
- Steps to reproduce
- Expected vs actual behavior
- Logs/screenshots
- Version and OS

## ✨ Requesting Features

Use our [feature request template](.github/ISSUE_TEMPLATE/feature_request.yml) and include:
- Problem you're trying to solve
- Proposed solution
- Alternative solutions considered

## 📬 Questions?

- 💬 Open a [Discussion](https://github.com/safal207/LiminalQAengineer/discussions)
- 🐛 File an [Issue](https://github.com/safal207/LiminalQAengineer/issues)
- 📧 Email: [your-email@example.com]

## 🙏 Recognition

All contributors will be:
- Listed in our README
- Thanked in release notes
- Forever appreciated! ❤️

---

_Thank you for making LiminalQA better!_ 🚀
