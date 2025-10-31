# Build stage
FROM rust:1.75-alpine AS builder

# Install build dependencies
RUN apk add --no-cache musl-dev openssl-dev pkgconfig

WORKDIR /app

# Copy manifests
COPY Cargo.toml ./

# Create dummy main to cache dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy source
COPY src ./src

# Build for release (force rebuild of actual code)
RUN touch src/main.rs && cargo build --release

# Runtime stage
FROM alpine:3.19

# Install runtime dependencies
RUN apk add --no-cache ca-certificates curl libgcc

WORKDIR /app

# Copy binary
COPY --from=builder /app/target/release/liminal-ingest /app/liminal-ingest

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8088/health || exit 1

EXPOSE 8088

CMD ["/app/liminal-ingest"]
