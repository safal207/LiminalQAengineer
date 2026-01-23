#!/bin/bash
set -e

echo "🔍 Running pre-push checks..."

echo "1️⃣ Format check..."
cargo fmt --all -- --check

echo "2️⃣ Clippy..."
cargo clippy --all-targets --all-features -- -D warnings

echo "3️⃣ Tests..."
cargo test --workspace

echo "4️⃣ Build..."
cargo build --release

echo "✅ All checks passed!"
