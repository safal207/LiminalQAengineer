FROM rust:1.90-bookworm AS builder

RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    libssl-dev \
    clang \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY . .

RUN cargo build --release -p liminalqa-ingest

FROM rust:1.90-bookworm

WORKDIR /app

COPY --from=builder /usr/src/app/target/release/liminalqa-ingest /usr/local/bin/liminalqa-ingest

EXPOSE 8088

ENTRYPOINT ["liminalqa-ingest"]
