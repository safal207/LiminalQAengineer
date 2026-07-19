#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [upstreamRoot, outputPath, upstreamSha] = process.argv.slice(2);
if (!upstreamRoot || !outputPath || !upstreamSha) {
  console.error("usage: node revolut_retry_after_docker_probe.mjs <upstream-root> <output> <upstream-sha>");
  process.exit(2);
}

const requestModuleUrl = pathToFileURL(
  path.join(upstreamRoot, "api", "dist", "http", "request.js"),
).href;
const { makeRequest } = await import(requestModuleUrl);

const logger = {
  debug() {},
  info() {},
  warn() {},
  error() {},
};

async function observeRetryAfter(headerValue) {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ message: "Rate limited" }), {
      status: 429,
      headers: {
        "Content-Type": "application/json",
        "Retry-After": headerValue,
      },
    });

  try {
    await makeRequest(
      {
        baseUrl: "https://example.invalid",
        timeout: 1000,
        maxRetries: 0,
        logger,
      },
      "GET",
      "/balances",
    );
    throw new Error("expected RateLimitError");
  } catch (error) {
    if (error?.name !== "RateLimitError") throw error;
    return {
      name: error.name,
      status_code: error.statusCode,
      retry_after: Number.isNaN(error.retryAfter) ? null : error.retryAfter,
      retry_after_is_nan: Number.isNaN(error.retryAfter),
    };
  }
}

const numeric = await observeRetryAfter("2");
const httpDate = await observeRetryAfter("Sun, 19 Jul 2026 00:00:02 GMT");

const result = {
  schema_version: "liminalqa-revolut-retry-after-docker-probe-v0.1",
  upstream_repository: "revolut-engineering/revolut-x-api",
  upstream_sha: upstreamSha,
  execution: {
    container_network: "none",
    authentication: false,
    account_access: false,
    live_revolut_request: false,
  },
  documentation_contract: {
    public_property: "RateLimitError.retryAfter",
    documented_unit: "milliseconds",
  },
  observations: {
    numeric_delay_seconds_header: {
      header: "2",
      observed: numeric,
      expected_if_milliseconds: 2000,
    },
    http_date_header: {
      header_kind: "HTTP-date",
      observed: httpDate,
      expected: "non-negative millisecond delay",
    },
  },
  classification:
    numeric.retry_after === 2 && httpDate.retry_after_is_nan
      ? "CONFIRMED_RETRY_AFTER_CONTRACT_MISMATCH"
      : "UPSTREAM_BEHAVIOR_CHANGED",
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ classification: result.classification }));
