#!/bin/bash
set -euo pipefail

echo "💖 Welcome to LiminalQA Development!"
echo ""

# Install Rust if not present
if ! command -v rustc &> /dev/null; then
    echo "📦 Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env
fi

echo "✅ Rust $(rustc --version) installed"

# Install development tools
echo "🔧 Installing development tools..."
cargo install cargo-watch
cargo install cargo-tarpaulin
cargo install cargo-audit
cargo install cargo-edit

# Setup pre-commit hooks
echo "🪝 Setting up git hooks..."
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
set -e

echo "🔍 Running pre-commit checks..."

# Format check
cargo fmt --all -- --check || {
    echo "❌ Code is not formatted. Run 'cargo fmt' and try again."
    exit 1
}

# Clippy
cargo clippy --all-targets -- -D warnings || {
    echo "❌ Clippy found issues. Fix them and try again."
    exit 1
}

# Tests
cargo test --workspace || {
    echo "❌ Tests failed. Fix them and try again."
    exit 1
}

echo "✅ All checks passed!"
EOF

chmod +x .git/hooks/pre-commit

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📚 Next steps:"
echo "  1. cargo test --workspace     # Run all tests"
echo "  2. cargo run -p liminalqa-ingest  # Start the server"
echo "  3. Read CONTRIBUTING.md for guidelines"
echo ""
echo "💖 Happy coding!"
