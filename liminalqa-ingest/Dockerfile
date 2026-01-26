FROM rust:1.90-bullseye AS builder

RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
COPY . .

# Build specific package
RUN cargo build --release -p liminalqa-ingest

# Runtime
FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/src/app/target/release/liminalqa-ingest /usr/local/bin/liminalqa-ingest

# Env
ENV RUST_LOG=info

EXPOSE 8080
EXPOSE 50051

ENTRYPOINT ["liminalqa-ingest"]
