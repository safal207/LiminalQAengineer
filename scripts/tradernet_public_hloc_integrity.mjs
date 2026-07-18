#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key}`);
    args[key.slice(2)] = value;
  }
  return args;
}

function round(value, digits = 3) {
  if (!Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function analyzeHloc(json, ticker) {
  const hloc = json?.hloc?.[ticker];
  const timestamps = json?.xSeries?.[ticker];
  const volumes = json?.vl?.[ticker];
  const violations = [];
  const add = (type, index = null, details = {}) => {
    if (violations.length < 100) violations.push({ type, index, ...details });
  };

  if (!Array.isArray(hloc)) add("HLOC_SERIES_MISSING");
  if (!Array.isArray(timestamps)) add("TIMESTAMP_SERIES_MISSING");
  if (!Array.isArray(volumes)) add("VOLUME_SERIES_MISSING");
  if (!Array.isArray(hloc) || !Array.isArray(timestamps) || !Array.isArray(volumes)) {
    return { candle_count: 0, timestamp_count: 0, volume_count: 0, violations };
  }

  if (hloc.length !== timestamps.length) {
    add("HLOC_TIMESTAMP_LENGTH_MISMATCH", null, { hloc: hloc.length, timestamps: timestamps.length });
  }
  if (hloc.length !== volumes.length) {
    add("HLOC_VOLUME_LENGTH_MISMATCH", null, { hloc: hloc.length, volumes: volumes.length });
  }

  const seen = new Set();
  let previous = null;
  let firstTimestamp = null;
  let lastTimestamp = null;
  let nonZeroVolumeCount = 0;

  hloc.forEach((row, index) => {
    if (!Array.isArray(row) || row.length < 4) {
      add("CANDLE_SHAPE_INVALID", index, { length: Array.isArray(row) ? row.length : null });
      return;
    }
    const [high, low, open, close] = row.map(Number);
    if (![high, low, open, close].every(Number.isFinite)) add("CANDLE_NON_NUMERIC", index);
    if (high < low) add("CANDLE_HIGH_BELOW_LOW", index);
    if (open < low || open > high) add("CANDLE_OPEN_OUTSIDE_RANGE", index);
    if (close < low || close > high) add("CANDLE_CLOSE_OUTSIDE_RANGE", index);
    if ([high, low, open, close].some((value) => value <= 0)) add("CANDLE_NON_POSITIVE_PRICE", index);

    const timestamp = Number(timestamps[index]);
    if (!Number.isFinite(timestamp)) {
      add("TIMESTAMP_NON_NUMERIC", index);
    } else {
      firstTimestamp ??= timestamp;
      lastTimestamp = timestamp;
      if (seen.has(timestamp)) add("TIMESTAMP_DUPLICATE", index);
      seen.add(timestamp);
      if (Number.isFinite(previous) && timestamp <= previous) add("TIMESTAMP_NOT_STRICTLY_INCREASING", index);
      previous = timestamp;
    }

    const volume = Number(volumes[index]);
    if (!Number.isFinite(volume)) add("VOLUME_NON_NUMERIC", index);
    if (volume < 0) add("VOLUME_NEGATIVE", index);
    if (volume > 0) nonZeroVolumeCount += 1;
  });

  const maxSeries = Number(json?.maxSeries);
  if (Number.isFinite(maxSeries) && Number.isFinite(lastTimestamp) && maxSeries !== lastTimestamp) {
    add("MAX_SERIES_DIFFERS_FROM_LAST_TIMESTAMP", null, {
      max_series: maxSeries,
      last_timestamp: lastTimestamp,
      delta_seconds: maxSeries - lastTimestamp,
    });
  }

  return {
    candle_count: hloc.length,
    timestamp_count: timestamps.length,
    volume_count: volumes.length,
    non_zero_volume_count: nonZeroVolumeCount,
    first_timestamp: firstTimestamp,
    first_timestamp_iso: Number.isFinite(firstTimestamp) ? new Date(firstTimestamp * 1000).toISOString() : null,
    last_timestamp: lastTimestamp,
    last_timestamp_iso: Number.isFinite(lastTimestamp) ? new Date(lastTimestamp * 1000).toISOString() : null,
    max_series: Number.isFinite(maxSeries) ? maxSeries : null,
    server_took_ms: Number.isFinite(Number(json?.took)) ? Number(json.took) : null,
    info_present: Boolean(json?.info?.[ticker]),
    violations,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  const desktop = config.profiles.find((profile) => profile.id === "desktop_broadband");
  if (!desktop || config.target_url !== "https://tradernet.ru/charts/MICEXINDEXCF") {
    throw new Error("Unexpected audit configuration");
  }

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(desktop.user_agent);
  await page.setViewport(desktop.viewport);
  await page.setCacheEnabled(false);

  const client = await page.createCDPSession();
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: desktop.network.latency_ms,
    downloadThroughput: desktop.network.download_bytes_per_second,
    uploadThroughput: desktop.network.upload_bytes_per_second,
    connectionType: desktop.network.connection_type,
  });

  let captured = null;
  let captureError = null;
  let requestShape = null;
  page.on("response", (response) => {
    if (captured || captureError || !response.url().includes("getHloc")) return;
    void (async () => {
      try {
        const url = new URL(response.url());
        const rawQuery = url.searchParams.get("q");
        if (rawQuery) {
          const requestJson = JSON.parse(rawQuery);
          requestShape = {
            cmd: requestJson.cmd,
            id: requestJson.params?.id,
            timeframe: requestJson.params?.timeframe,
            interval: requestJson.params?.interval,
            interval_mode: requestJson.params?.intervalMode,
            date_from: requestJson.params?.date_from,
            date_to: requestJson.params?.date_to,
            count: requestJson.params?.count,
            demo: requestJson.params?.demo,
          };
        }
        const json = await response.json();
        captured = {
          url: response.url(),
          status: response.status(),
          analysis: analyzeHloc(json, config.ticker),
        };
      } catch (error) {
        captureError = String(error?.stack || error);
      }
    })();
  });

  let navigationError = null;
  const started = performance.now();
  try {
    await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  } catch (error) {
    navigationError = String(error?.stack || error);
  }

  const deadline = Date.now() + 35_000;
  while (!captured && !captureError && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const elapsedMs = round(performance.now() - started);
  await fs.mkdir(args["output-dir"], { recursive: true });
  await page.screenshot({ path: path.join(args["output-dir"], "hloc-page.png"), fullPage: true });

  const result = {
    schema_version: "liminalqa-public-hloc-integrity-result-v1",
    target_url: config.target_url,
    final_url: page.url(),
    ticker: config.ticker,
    navigation_error: navigationError,
    capture_error: captureError,
    observed_within_ms: elapsedMs,
    request_shape: requestShape,
    response: captured,
    verdict:
      navigationError || captureError || !captured
        ? "EVIDENCE_FAILURE"
        : captured.analysis.violations.length > 0
          ? "WARN"
          : "PASS",
    generated_at: new Date().toISOString(),
  };

  const jsonPath = path.join(args["output-dir"], "hloc-integrity-result.json");
  await fs.writeFile(jsonPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  const analysis = captured?.analysis;
  const markdown = [
    "# Tradernet public HLOC integrity",
    "",
    `**Verdict:** ${result.verdict}  `,
    `**Ticker:** ${config.ticker}  `,
    `**Observed within:** ${elapsedMs} ms`,
    "",
    "| Candles | Timestamps | Volumes | First candle | Last candle | Violations |",
    "|---:|---:|---:|---|---|---:|",
    `| ${analysis?.candle_count ?? 0} | ${analysis?.timestamp_count ?? 0} | ${analysis?.volume_count ?? 0} | ${analysis?.first_timestamp_iso ?? "n/a"} | ${analysis?.last_timestamp_iso ?? "n/a"} | ${analysis?.violations.length ?? 0} |`,
    "",
    "> The response was captured only because the public chart page naturally requested it. No direct API request was issued by the audit.",
    "",
  ].join("\n");
  await fs.writeFile(path.join(args["output-dir"], "hloc-integrity-summary.md"), markdown, "utf8");

  await context.close();
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
  if (result.verdict === "EVIDENCE_FAILURE") process.exitCode = 1;
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
