#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    }
    args[key.slice(2)] = value;
  }
  return args;
}

function round(value, digits = 3) {
  if (!Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function clip(value, limit = 500) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : `${text.slice(0, limit)}…`;
}

function numberFrom(object, keys) {
  for (const key of keys) {
    const value = object?.[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function timeFrom(object) {
  const rawKeys = ["timestamp", "time", "datetime", "date", "t", "x", "ts"];
  for (const key of rawKeys) {
    const value = object?.[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value < 10_000_000_000 ? value * 1000 : value;
    }
    if (typeof value === "string") {
      const numeric = Number(value);
      if (Number.isFinite(numeric)) return numeric < 10_000_000_000 ? numeric * 1000 : numeric;
      const parsed = Date.parse(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
}

function scanJson(root) {
  const result = {
    arrays_scanned: 0,
    candle_arrays: 0,
    candles_seen: 0,
    quote_objects: 0,
    violations: [],
    observed_keys: new Set(),
  };

  const addViolation = (type, jsonPath, details = {}) => {
    if (result.violations.length < 30) result.violations.push({ type, path: jsonPath, ...details });
  };

  const inspectArray = (items, jsonPath) => {
    result.arrays_scanned += 1;
    const objects = items.filter((item) => item && typeof item === "object" && !Array.isArray(item));
    if (objects.length === 0) return;

    const candleRows = objects
      .map((item, index) => ({
        index,
        item,
        open: numberFrom(item, ["open", "o"]),
        high: numberFrom(item, ["high", "h"]),
        low: numberFrom(item, ["low"]),
        close: numberFrom(item, ["close", "c"]),
        timestamp: timeFrom(item),
      }))
      .filter(
        (row) =>
          Number.isFinite(row.open) &&
          Number.isFinite(row.high) &&
          Number.isFinite(row.low) &&
          Number.isFinite(row.close)
      );

    if (candleRows.length >= 2) {
      result.candle_arrays += 1;
      result.candles_seen += candleRows.length;
      let previousTimestamp = null;
      const timestamps = new Set();
      for (const row of candleRows) {
        const rowPath = `${jsonPath}[${row.index}]`;
        if (row.high < row.low) addViolation("CANDLE_HIGH_BELOW_LOW", rowPath);
        if (row.open < row.low || row.open > row.high) addViolation("CANDLE_OPEN_OUTSIDE_RANGE", rowPath);
        if (row.close < row.low || row.close > row.high) addViolation("CANDLE_CLOSE_OUTSIDE_RANGE", rowPath);
        if ([row.open, row.high, row.low, row.close].some((value) => value <= 0)) {
          addViolation("CANDLE_NON_POSITIVE_PRICE", rowPath);
        }
        if (Number.isFinite(row.timestamp)) {
          if (timestamps.has(row.timestamp)) addViolation("CANDLE_DUPLICATE_TIMESTAMP", rowPath);
          timestamps.add(row.timestamp);
          if (Number.isFinite(previousTimestamp) && row.timestamp < previousTimestamp) {
            addViolation("CANDLE_TIMESTAMP_REGRESSION", rowPath);
          }
          previousTimestamp = row.timestamp;
        }
      }
    }
  };

  const visit = (value, jsonPath, depth) => {
    if (depth > 14 || value === null || value === undefined) return;
    if (Array.isArray(value)) {
      inspectArray(value, jsonPath);
      value.forEach((item, index) => visit(item, `${jsonPath}[${index}]`, depth + 1));
      return;
    }
    if (typeof value !== "object") return;

    Object.keys(value).slice(0, 100).forEach((key) => result.observed_keys.add(key));

    const bid = numberFrom(value, ["bid", "bestBid", "bidPrice"]);
    const ask = numberFrom(value, ["ask", "bestAsk", "askPrice"]);
    const last = numberFrom(value, ["last", "lastPrice", "ltp", "price"]);
    const high = numberFrom(value, ["dayHigh", "high", "hi"]);
    const low = numberFrom(value, ["dayLow", "low", "lo"]);
    const previousClose = numberFrom(value, ["prevClose", "previousClose", "closePrev"]);
    const changePercent = numberFrom(value, ["changePercent", "changePct", "percentChange", "pc"]);

    if ([bid, ask, last].some(Number.isFinite)) {
      result.quote_objects += 1;
      if (Number.isFinite(bid) && Number.isFinite(ask) && bid > ask) {
        addViolation("QUOTE_BID_ABOVE_ASK", jsonPath);
      }
      if (Number.isFinite(last) && Number.isFinite(low) && last < low) {
        addViolation("QUOTE_LAST_BELOW_DAY_LOW", jsonPath);
      }
      if (Number.isFinite(last) && Number.isFinite(high) && last > high) {
        addViolation("QUOTE_LAST_ABOVE_DAY_HIGH", jsonPath);
      }
      if (
        Number.isFinite(last) &&
        Number.isFinite(previousClose) &&
        previousClose !== 0 &&
        Number.isFinite(changePercent)
      ) {
        const computed = ((last - previousClose) / previousClose) * 100;
        if (Math.abs(computed - changePercent) > 0.2) {
          addViolation("QUOTE_CHANGE_PERCENT_MISMATCH", jsonPath, {
            delta_percentage_points: round(Math.abs(computed - changePercent), 4),
          });
        }
      }
    }

    for (const [key, child] of Object.entries(value)) visit(child, `${jsonPath}.${key}`, depth + 1);
  };

  visit(root, "$", 0);
  return {
    arrays_scanned: result.arrays_scanned,
    candle_arrays: result.candle_arrays,
    candles_seen: result.candles_seen,
    quote_objects: result.quote_objects,
    violations: result.violations,
    observed_keys: [...result.observed_keys].sort().slice(0, 150),
  };
}

async function captureDom(page) {
  return page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 2 && rect.height > 2 && style.display !== "none" && style.visibility !== "hidden";
    };
    const serialize = (element) => {
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName,
        id: element.id || null,
        class: typeof element.className === "string" ? element.className.slice(0, 300) : null,
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        visible: visible(element),
      };
    };
    const canvases = [...document.querySelectorAll("canvas")].map((canvas) => ({
      ...serialize(canvas),
      pixel_width: canvas.width,
      pixel_height: canvas.height,
    }));
    const svgs = [...document.querySelectorAll("svg")].map(serialize);
    const chartCandidates = [
      ...document.querySelectorAll(
        '[id*="chart" i], [class*="chart" i], [id*="graph" i], [class*="graph" i], [class*="highcharts" i], [class*="tradingview" i]'
      ),
    ]
      .slice(0, 100)
      .map(serialize);
    const frames = [...document.querySelectorAll("iframe")].map((frame) => ({
      ...serialize(frame),
      src: frame.src || null,
    }));
    const timeframeLabels = [...document.querySelectorAll("button, a, [role=button], span, div")]
      .filter((element) => ["1m", "5m", "3M", "YTD", "1Y", "5Y", "MAX"].includes(element.textContent?.trim()))
      .slice(0, 50)
      .map((element) => ({ text: element.textContent.trim(), ...serialize(element) }));
    const bodyText = document.body?.innerText || "";
    const statusMatches = bodyText
      .split(/\n+/)
      .map((line) => line.trim())
      .filter((line) => /ошиб|error|нет данных|no data|загруз|loading|market closed|рынок закрыт/i.test(line))
      .slice(0, 30);
    const visibleChartSurface = [...canvases, ...svgs, ...chartCandidates].some(
      (item) => item.visible && item.width >= 120 && item.height >= 80
    );
    return {
      url: location.href,
      title: document.title,
      ready_state: document.readyState,
      canvases,
      svgs,
      chart_candidates: chartCandidates,
      iframes: frames,
      timeframe_labels: timeframeLabels,
      status_messages: statusMatches,
      visible_chart_surface: visibleChartSurface,
      body_text_sha256_input: bodyText.slice(0, 100_000),
    };
  });
}

async function clickTimeframe(page, label) {
  return page.evaluate((target) => {
    const elements = [...document.querySelectorAll("button, a, [role=button], span, div")];
    const candidate = elements.find((element) => {
      if (element.textContent?.trim() !== target) return false;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 1 && rect.height > 1 && style.display !== "none" && style.visibility !== "hidden";
    });
    if (!candidate) return { clicked: false, reason: "not_found" };
    candidate.click();
    return {
      clicked: true,
      tag: candidate.tagName,
      id: candidate.id || null,
      class: typeof candidate.className === "string" ? candidate.className.slice(0, 200) : null,
    };
  }, label);
}

async function runProfile(browser, config, profile, outputDir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.setCacheEnabled(false);

  const consoleMessages = [];
  const pageErrors = [];
  const failedRequests = [];
  const responses = [];
  const parsedBodies = [];
  const responseTasks = [];
  const websocket = {
    created: [],
    closed: [],
    received_frames: 0,
    sent_frames: 0,
    ticker_matching_frames: 0,
    received_bytes: 0,
    first_received_at: null,
    last_received_at: null,
  };

  page.on("console", (message) => {
    if (consoleMessages.length < 200) {
      consoleMessages.push({ type: message.type(), text: clip(message.text(), 1000) });
    }
  });
  page.on("pageerror", (error) => {
    if (pageErrors.length < 100) pageErrors.push(clip(error?.stack || error, 2000));
  });
  page.on("requestfailed", (request) => {
    if (failedRequests.length < 200) {
      failedRequests.push({
        url: request.url(),
        resource_type: request.resourceType(),
        error: request.failure()?.errorText || null,
      });
    }
  });
  page.on("response", (response) => {
    const request = response.request();
    const headers = response.headers();
    const entry = {
      url: response.url(),
      status: response.status(),
      resource_type: request.resourceType(),
      content_type: headers["content-type"] || null,
      content_length: headers["content-length"] || null,
    };
    if (responses.length < 500) responses.push(entry);

    const sameTradernet = /^https:\/\/[^/]*tradernet\.(ru|com|global|am)\//i.test(response.url());
    const bodyCandidate = ["xhr", "fetch"].includes(request.resourceType()) && sameTradernet;
    if (!bodyCandidate || parsedBodies.length >= 80) return;

    responseTasks.push(
      (async () => {
        try {
          const contentType = headers["content-type"] || "";
          if (!/json|javascript|text\/plain/i.test(contentType)) return;
          const text = await response.text();
          if (text.length > 2_000_000) return;
          const record = {
            url: response.url(),
            status: response.status(),
            bytes: Buffer.byteLength(text),
            sha256: sha256(text),
            parsed_json: false,
            json_scan: null,
          };
          try {
            const json = JSON.parse(text);
            record.parsed_json = true;
            record.json_scan = scanJson(json);
          } catch {
            // Public responses can be JavaScript or newline-delimited payloads.
          }
          parsedBodies.push(record);
        } catch (error) {
          parsedBodies.push({
            url: response.url(),
            status: response.status(),
            body_read_error: clip(error?.message || error),
          });
        }
      })()
    );
  });

  const client = await page.createCDPSession();
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: profile.network.latency_ms,
    downloadThroughput: profile.network.download_bytes_per_second,
    uploadThroughput: profile.network.upload_bytes_per_second,
    connectionType: profile.network.connection_type,
  });
  await client.send("Emulation.setCPUThrottlingRate", { rate: profile.cpu_throttling_rate });
  client.on("Network.webSocketCreated", (event) => {
    if (websocket.created.length < 50) websocket.created.push({ request_id: event.requestId, url: event.url });
  });
  client.on("Network.webSocketClosed", (event) => {
    if (websocket.closed.length < 50) websocket.closed.push({ request_id: event.requestId, at: event.timestamp });
  });
  client.on("Network.webSocketFrameReceived", (event) => {
    const payload = event.response?.payloadData || "";
    websocket.received_frames += 1;
    websocket.received_bytes += Buffer.byteLength(payload);
    websocket.first_received_at ??= new Date().toISOString();
    websocket.last_received_at = new Date().toISOString();
    if (payload.includes(config.ticker)) websocket.ticker_matching_frames += 1;
  });
  client.on("Network.webSocketFrameSent", () => {
    websocket.sent_frames += 1;
  });

  const startedAt = new Date().toISOString();
  const startedMonotonic = performance.now();
  let navigationError = null;
  try {
    await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  } catch (error) {
    navigationError = clip(error?.stack || error, 3000);
  }

  let chartVisibleAtMs = null;
  if (!navigationError) {
    const deadline = Date.now() + config.observation_ms;
    while (Date.now() < deadline) {
      const visible = await page.evaluate(() => {
        const elements = document.querySelectorAll(
          'canvas, svg, [id*="chart" i], [class*="chart" i], [id*="graph" i], [class*="graph" i]'
        );
        return [...elements].some((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return rect.width >= 120 && rect.height >= 80 && style.display !== "none" && style.visibility !== "hidden";
        });
      });
      if (visible) {
        chartVisibleAtMs = round(performance.now() - startedMonotonic);
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  await new Promise((resolve) => setTimeout(resolve, Math.min(config.observation_ms, 15_000)));
  const before = await captureDom(page);
  before.body_text_sha256 = sha256(before.body_text_sha256_input);
  delete before.body_text_sha256_input;
  await page.screenshot({ path: path.join(outputDir, `${profile.id}-before.png`), fullPage: true });

  const timeframeAction = await clickTimeframe(page, config.timeframe_probe);
  if (timeframeAction.clicked) await new Promise((resolve) => setTimeout(resolve, 8_000));
  const after = await captureDom(page);
  after.body_text_sha256 = sha256(after.body_text_sha256_input);
  delete after.body_text_sha256_input;
  await page.screenshot({ path: path.join(outputDir, `${profile.id}-after-${config.timeframe_probe}.png`), fullPage: true });

  await Promise.allSettled(responseTasks);
  const navigationTiming = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    if (!navigation) return null;
    return {
      response_start_ms: navigation.responseStart,
      response_end_ms: navigation.responseEnd,
      dom_content_loaded_ms: navigation.domContentLoadedEventEnd,
      load_event_ms: navigation.loadEventEnd,
      transfer_size: navigation.transferSize,
    };
  });

  const combinedScan = {
    candle_arrays: 0,
    candles_seen: 0,
    quote_objects: 0,
    violations: [],
  };
  for (const body of parsedBodies) {
    if (!body.json_scan) continue;
    combinedScan.candle_arrays += body.json_scan.candle_arrays;
    combinedScan.candles_seen += body.json_scan.candles_seen;
    combinedScan.quote_objects += body.json_scan.quote_objects;
    for (const violation of body.json_scan.violations) {
      if (combinedScan.violations.length < 50) {
        combinedScan.violations.push({ url: body.url, ...violation });
      }
    }
  }

  const day = new Date().getUTCDay();
  const weekend = day === 0 || day === 6;
  const liveQuoteAssessment = weekend
    ? "NOT_ASSESSED_WEEKEND"
    : websocket.ticker_matching_frames > 0
      ? "OBSERVED"
      : "INCONCLUSIVE_NO_TICKER_FRAME";
  const historicalAssessment = combinedScan.candles_seen > 0
    ? "PARSED_AND_CHECKED"
    : before.visible_chart_surface || after.visible_chart_surface
      ? "VISUAL_SURFACE_ONLY"
      : "NOT_OBSERVED";

  const warningSignals = [
    navigationError,
    !before.visible_chart_surface && !after.visible_chart_surface ? "NO_VISIBLE_CHART_SURFACE" : null,
    pageErrors.length > 0 ? "PAGE_ERRORS" : null,
    failedRequests.some((item) => ["xhr", "fetch", "websocket"].includes(item.resource_type))
      ? "MARKET_DATA_REQUEST_FAILURE"
      : null,
    combinedScan.violations.length > 0 ? "DATA_INVARIANT_VIOLATIONS" : null,
    !timeframeAction.clicked ? "TIMEFRAME_CONTROL_NOT_FOUND" : null,
  ].filter(Boolean);

  const result = {
    schema_version: "liminalqa-public-market-data-profile-result-v1",
    profile: profile.id,
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    target_url: config.target_url,
    final_url: page.url(),
    ticker: config.ticker,
    verdict: warningSignals.length === 0 ? "OBSERVED" : "WARN",
    warning_signals: warningSignals,
    navigation_error: navigationError,
    chart_visible_at_ms: chartVisibleAtMs,
    navigation_timing: navigationTiming,
    timeframe_action: timeframeAction,
    dom_before: before,
    dom_after: after,
    console_messages: consoleMessages,
    page_errors: pageErrors,
    failed_requests: failedRequests,
    responses,
    parsed_public_response_bodies: parsedBodies,
    data_invariant_summary: combinedScan,
    websocket,
    assessments: {
      historical_chart_loading: historicalAssessment,
      live_quote_liveness: liveQuoteAssessment,
      market_window_note: weekend
        ? "Run occurred during a UTC weekend; absent live updates are not classified as a bug."
        : "Trading-session status was not independently verified.",
    },
  };

  await fs.writeFile(
    path.join(outputDir, `${profile.id}-result.json`),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8"
  );
  await context.close();
  return result;
}

function renderMarkdown(packet) {
  const lines = [
    "# LiminalQA · Tradernet public charts and quotes",
    "",
    `**Verdict:** ${packet.verdict}  `,
    `**Target:** ${packet.config.target_url}  `,
    `**Ticker:** ${packet.config.ticker}`,
    "",
    "## Profile results",
    "",
    "| Profile | Chart visible | Visible at | Historical data | Live quotes | Page errors | Failed requests | Invariant findings |",
    "|---|---:|---:|---|---|---:|---:|---:|",
  ];
  for (const result of packet.results) {
    lines.push(
      `| ${result.profile} | ${result.dom_before.visible_chart_surface || result.dom_after.visible_chart_surface ? "yes" : "no"} | ` +
        `${result.chart_visible_at_ms ?? "n/a"} ms | ${result.assessments.historical_chart_loading} | ` +
        `${result.assessments.live_quote_liveness} | ${result.page_errors.length} | ` +
        `${result.failed_requests.length} | ${result.data_invariant_summary.violations.length} |`
    );
  }
  lines.push("", "## Causal test map", "", "```text");
  lines.push("Public chart navigation");
  lines.push("  → document and shared runtime");
  lines.push("  → chart surface creation");
  lines.push("  → public historical-data responses");
  lines.push("  → candle/quote invariant checks");
  lines.push("  → one bounded timeframe switch");
  lines.push("  → WebSocket observation without direct subscription");
  lines.push("  → evidence-backed next experiments");
  lines.push("```", "");
  lines.push(
    "> The run is passive and public-page-only. It does not authenticate, call application APIs directly, subscribe to market depth, place orders, fuzz symbols, or classify absent weekend quotes as a defect.",
    ""
  );
  return lines.join("\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  if (config.target_url !== "https://tradernet.ru/charts/MICEXINDEXCF") {
    throw new Error("Unexpected target URL");
  }
  if (config.profiles.length !== 2 || config.observation_ms > 30_000) {
    throw new Error("Audit boundary exceeded");
  }

  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });

  const results = [];
  try {
    for (const profile of config.profiles) {
      results.push(await runProfile(browser, config, profile, args["output-dir"]));
    }
  } finally {
    await browser.close();
  }

  const warnings = results.flatMap((result) => result.warning_signals.map((signal) => ({
    profile: result.profile,
    signal,
  })));
  const packet = {
    schema_version: "liminalqa-public-market-data-audit-result-v1",
    verdict: warnings.length === 0 ? "OBSERVED" : "WARN",
    config,
    results,
    warnings,
    generated_at: new Date().toISOString(),
  };
  const resultDir = path.join(args["output-dir"], "result");
  await fs.mkdir(resultDir, { recursive: true });
  await fs.writeFile(
    path.join(resultDir, "chart-quote-result.json"),
    `${JSON.stringify(packet, null, 2)}\n`,
    "utf8"
  );
  await fs.writeFile(
    path.join(resultDir, "chart-quote-summary.md"),
    renderMarkdown(packet),
    "utf8"
  );
  console.log(JSON.stringify({ verdict: packet.verdict, warnings, results: results.map((result) => ({
    profile: result.profile,
    chart_visible_at_ms: result.chart_visible_at_ms,
    historical: result.assessments.historical_chart_loading,
    live_quotes: result.assessments.live_quote_liveness,
    page_errors: result.page_errors.length,
    failed_requests: result.failed_requests.length,
    invariants: result.data_invariant_summary.violations.length,
    websocket_frames: result.websocket.received_frames,
  })) }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
