FROM rust:1.90-bookworm AS builder

RUN apt-get update -o Acquire::Retries=5 && apt-get install -y --no-install-recommends \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY . .

RUN cargo build --release -p liminalqa-ingest

FROM rust:1.90-bookworm

WORKDIR /app

COPY --from=builder /usr/src/app/target/release/liminalqa-ingest /usr/local/bin/liminalqa-ingest

EXPOSE 8088

ENTRYPOINT ["liminalqa-ingest"]
