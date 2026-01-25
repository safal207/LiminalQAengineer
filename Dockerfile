FROM rust:1.90-bullseye AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    libssl-dev \
    clang \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Copy project files
COPY . .

# Build the project
RUN cargo build --release

# Production stage
FROM debian:bullseye-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binaries
COPY --from=builder /usr/src/app/target/release/limctl /usr/local/bin/limctl
COPY --from=builder /usr/src/app/target/release/liminalqa-ingest /usr/local/bin/liminalqa-ingest

# Create data directory
RUN mkdir -p /app/data

# Set the entrypoint
ENTRYPOINT ["liminalqa-ingest"]
