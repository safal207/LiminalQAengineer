.PHONY: help build test lint fmt clean doc bench coverage

# Default target
.DEFAULT_GOAL := help

# Colors
CYAN := \033[36m
RESET := \033[0m

help: ## Show this help message
	@echo "$(CYAN)LiminalQA Makefile Commands$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-15s$(RESET) %s\n", $$1, $$2}'

build: ## Build all packages
	@echo "🏗️  Building..."
	@cargo build --workspace

build-release: ## Build release binaries
	@echo "🏗️  Building release..."
	@cargo build --workspace --release

test: ## Run all tests
	@echo "🧪 Running tests..."
	@cargo test --workspace --verbose

test-watch: ## Run tests in watch mode
	@echo "👀 Watching tests..."
	@cargo watch -x "test --workspace"

lint: ## Run clippy
	@echo "📎 Running clippy..."
	@cargo clippy --all-targets --all-features -- -D warnings

fmt: ## Format code
	@echo "💅 Formatting..."
	@cargo fmt --all

fmt-check: ## Check formatting
	@echo "🔍 Checking format..."
	@cargo fmt --all -- --check

clean: ## Clean build artifacts
	@echo "🧹 Cleaning..."
	@cargo clean

doc: ## Build documentation
	@echo "📚 Building docs..."
	@cargo doc --no-deps --workspace --all-features --open

bench: ## Run benchmarks
	@echo "⚡ Running benchmarks..."
	@cargo bench --workspace

coverage: ## Generate code coverage
	@echo "📊 Generating coverage..."
	@cargo tarpaulin --workspace --out Html --output-dir coverage
	@echo "📊 Coverage report: coverage/index.html"

audit: ## Run security audit
	@echo "🔒 Running security audit..."
	@cargo audit

ci: fmt-check lint test ## Run CI checks locally
	@echo "✅ All CI checks passed!"

dev: ## Start development server
	@echo "🚀 Starting dev server..."
	@LIMINAL_AUTH_TOKEN=dev-token cargo run -p liminalqa-ingest

docker-build: ## Build Docker image
	@echo "🐋 Building Docker image..."
	@docker build -t liminalqa-ingest:latest -f liminalqa-ingest/Dockerfile .

docker-run: ## Run Docker container
	@echo "🐋 Running Docker container..."
	@docker run -p 8080:8080 -e LIMINAL_AUTH_TOKEN=test liminalqa-ingest:latest

all: fmt lint test build ## Run all checks and build
	@echo "✅ Everything complete!"
