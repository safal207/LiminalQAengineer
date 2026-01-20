# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM rust:1.75-slim as builder

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy workspace
COPY Cargo.toml Cargo.lock ./
COPY liminalqa-core ./liminalqa-core
COPY liminalqa-db ./liminalqa-db
COPY liminalqa-ingest ./liminalqa-ingest

# Build with optimizations
RUN cargo build --release --package liminalqa-ingest

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 liminal

# Copy binary
COPY --from=builder /app/target/release/liminalqa-ingest /usr/local/bin/

# Create data directory
RUN mkdir -p /var/lib/liminal && chown liminal:liminal /var/lib/liminal

USER liminal
WORKDIR /home/liminal

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/usr/local/bin/liminalqa-ingest", "--health-check"]

ENV RUST_LOG=info
ENV LIMINAL_DB_PATH=/var/lib/liminal/db

ENTRYPOINT ["/usr/local/bin/liminalqa-ingest"]
