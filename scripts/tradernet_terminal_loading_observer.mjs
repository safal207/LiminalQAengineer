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
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    }
    args[key.slice(2)] = value;
  }
  return args;
}

function round(value, digits = 1) {
  if (!Number.isFinite(value)) return null;
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function normalizeError(error) {
  return String(error?.stack || error).slice(0, 2000);
}

function isFirstParty(url) {
  try {
    const host = new URL(url).hostname;
    return host === "tradernet.ru" || host.endsWith(".tradernet.ru");
  } catch {
    return false;
  }
}

async function installPerformanceObservers(page) {
  await page.evaluateOnNewDocument(() => {
    window.__liminalqaTerminal = {
      lcp: null,
      longTasks: [],
      observerErrors: [],
    };
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__liminalqaTerminal.lcp = {
            startTime: entry.startTime,
            renderTime: entry.renderTime,
            loadTime: entry.loadTime,
            size: entry.size,
            url: entry.url || null,
            elementTag: entry.element?.tagName || null,
            elementClass:
              typeof entry.element?.className === "string"
                ? entry.element.className.slice(0, 200)
                : null,
          };
        }
      }).observe({ type: "largest-contentful-paint", buffered: true });
    } catch (error) {
      window.__liminalqaTerminal.observerErrors.push(String(error));
    }
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__liminalqaTerminal.longTasks.push({
            startTime: entry.startTime,
            duration: entry.duration,
          });
        }
      }).observe({ type: "longtask", buffered: true });
    } catch (error) {
      window.__liminalqaTerminal.observerErrors.push(String(error));
    }
  });
}

async function collectDomState(page) {
  return page.evaluate(() => {
    const visible = (element, minWidth = 4, minHeight = 4) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rect.width >= minWidth &&
        rect.height >= minHeight &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0
      );
    };

    const bodyText = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const lower = bodyText.toLowerCase();
    const routeError =
      /(^|\s)404(\s|$)/.test(lower) ||
      lower.includes("страница не найдена") ||
      lower.includes("page not found");
    const authWall =
      /войти|регистрац|открыть сч[её]т|sign in|log in|create account/i.test(bodyText);
    const terminalTokens = [
      /терминал/i,
      /портфел/i,
      /котиров/i,
      /график/i,
      /заявк/i,
      /инструмент/i,
      /сделк/i,
      /позици/i,
      /order/i,
      /portfolio/i,
      /quote/i,
    ].filter((pattern) => pattern.test(bodyText)).length;

    const chartSurfaces = [
      ...document.querySelectorAll(
        'canvas, svg, [id*="chart" i], [class*="chart" i], [id*="graph" i], [class*="graph" i]'
      ),
    ].filter((element) => visible(element, 120, 80));
    const terminalSurfaces = [
      ...document.querySelectorAll(
        '[id*="terminal" i], [class*="terminal" i], [data-testid*="terminal" i], [id*="trade" i], [class*="trade" i]'
      ),
    ].filter((element) => visible(element, 120, 60));
    const spinners = [
      ...document.querySelectorAll(
        '[class*="spinner" i], [class*="loader" i], [aria-busy="true"], [role="progressbar"]'
      ),
    ].filter((element) => visible(element));

    const useful =
      !routeError &&
      (chartSurfaces.length > 0 ||
        terminalSurfaces.length > 0 ||
        terminalTokens >= 2 ||
        authWall);

    return {
      title: document.title,
      final_url: location.href,
      body_text_length: bodyText.length,
      body_text_sample: bodyText.slice(0, 1000),
      route_error: routeError,
      auth_wall: authWall,
      terminal_token_count: terminalTokens,
      chart_surface_count: chartSurfaces.length,
      terminal_surface_count: terminalSurfaces.length,
      spinner_count: spinners.length,
      useful_ui: useful,
    };
  });
}

async function collectPerformance(page) {
  return page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    const paints = performance.getEntriesByType("paint");
    const fcp = paints.find((entry) => entry.name === "first-contentful-paint");
    const resources = performance.getEntriesByType("resource");
    const longTasks = window.__liminalqaTerminal?.longTasks || [];
    const longTaskTotal = longTasks.reduce((sum, entry) => sum + entry.duration, 0);
    return {
      navigation: navigation
        ? {
            response_start_ms: navigation.responseStart,
            response_end_ms: navigation.responseEnd,
            dom_content_loaded_ms: navigation.domContentLoadedEventEnd,
            load_event_ms: navigation.loadEventEnd,
            transfer_size: navigation.transferSize,
            encoded_body_size: navigation.encodedBodySize,
          }
        : null,
      first_contentful_paint_ms: fcp?.startTime ?? null,
      largest_contentful_paint: window.__liminalqaTerminal?.lcp || null,
      long_task_count: longTasks.length,
      long_task_total_ms: longTaskTotal,
      resource_entry_count: resources.length,
      observer_errors: window.__liminalqaTerminal?.observerErrors || [],
    };
  });
}

function summarizeNetwork(requests, failedRequests) {
  const completed = [...requests.values()].filter((item) => Number.isFinite(item.encoded_bytes));
  const totals = completed.reduce(
    (acc, item) => {
      const type = item.type || "Other";
      acc.total_requests += 1;
      acc.total_encoded_bytes += item.encoded_bytes || 0;
      acc.by_type[type] ??= { requests: 0, encoded_bytes: 0 };
      acc.by_type[type].requests += 1;
      acc.by_type[type].encoded_bytes += item.encoded_bytes || 0;
      if (isFirstParty(item.url)) {
        acc.first_party_requests += 1;
        acc.first_party_encoded_bytes += item.encoded_bytes || 0;
      }
      return acc;
    },
    {
      total_requests: 0,
      total_encoded_bytes: 0,
      first_party_requests: 0,
      first_party_encoded_bytes: 0,
      by_type: {},
    }
  );

  const topResources = completed
    .sort((left, right) => (right.encoded_bytes || 0) - (left.encoded_bytes || 0))
    .slice(0, 20)
    .map((item) => ({
      url: item.url,
      type: item.type,
      status: item.status,
      mime_type: item.mime_type,
      encoded_bytes: item.encoded_bytes,
      first_party: isFirstParty(item.url),
    }));

  return {
    ...totals,
    failed_request_count: failedRequests.length,
    first_party_failed_request_count: failedRequests.filter((item) => isFirstParty(item.url)).length,
    top_resources: topResources,
  };
}

async function runProfile(browser, config, profile, outputDir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.setCacheEnabled(false);
  await installPerformanceObservers(page);

  const consoleEvents = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleEvents.push({ type: message.type(), text: message.text().slice(0, 2000) });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(normalizeError(error)));
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      method: request.method(),
      resource_type: request.resourceType(),
      error_text: request.failure()?.errorText || null,
    });
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

  const requests = new Map();
  const webSockets = new Map();
  client.on("Network.requestWillBeSent", (event) => {
    requests.set(event.requestId, {
      request_id: event.requestId,
      url: event.request.url,
      method: event.request.method,
      type: event.type || null,
      timestamp: event.timestamp,
      status: null,
      mime_type: null,
      encoded_bytes: null,
    });
  });
  client.on("Network.responseReceived", (event) => {
    const item = requests.get(event.requestId);
    if (!item) return;
    item.status = event.response.status;
    item.mime_type = event.response.mimeType;
    item.from_disk_cache = event.response.fromDiskCache;
    item.from_service_worker = event.response.fromServiceWorker;
  });
  client.on("Network.loadingFinished", (event) => {
    const item = requests.get(event.requestId);
    if (item) item.encoded_bytes = event.encodedDataLength;
  });
  client.on("Network.loadingFailed", (event) => {
    const item = requests.get(event.requestId);
    if (item) {
      item.loading_failed = true;
      item.failure_text = event.errorText;
    }
  });
  client.on("Network.webSocketCreated", (event) => {
    webSockets.set(event.requestId, {
      url: event.url,
      created: 1,
      closed: 0,
      received_frames: 0,
      sent_frames: 0,
      received_bytes: 0,
      sent_bytes: 0,
      errors: [],
    });
  });
  client.on("Network.webSocketFrameReceived", (event) => {
    const socket = webSockets.get(event.requestId);
    if (!socket) return;
    socket.received_frames += 1;
    socket.received_bytes += event.response.payloadData?.length || 0;
  });
  client.on("Network.webSocketFrameSent", (event) => {
    const socket = webSockets.get(event.requestId);
    if (!socket) return;
    socket.sent_frames += 1;
    socket.sent_bytes += event.response.payloadData?.length || 0;
  });
  client.on("Network.webSocketClosed", (event) => {
    const socket = webSockets.get(event.requestId);
    if (socket) socket.closed += 1;
  });
  client.on("Network.webSocketFrameError", (event) => {
    const socket = webSockets.get(event.requestId);
    if (socket) socket.errors.push(event.errorMessage);
  });

  const startedAt = new Date().toISOString();
  const wallStarted = Date.now();
  let navigationError = null;
  let navigationStatus = null;
  let firstUsefulUiMs = null;
  let firstChartSurfaceMs = null;
  let navigationResponse = null;
  try {
    navigationResponse = await page.goto(config.target_url, {
      waitUntil: "domcontentloaded",
      timeout: 90_000,
    });
    navigationStatus = navigationResponse?.status() ?? null;
  } catch (error) {
    navigationError = normalizeError(error);
  }

  const deadline = wallStarted + config.observation_ms;
  let state = await collectDomState(page);
  while (Date.now() < deadline) {
    const elapsed = Date.now() - wallStarted;
    if (firstUsefulUiMs === null && state.useful_ui) firstUsefulUiMs = elapsed;
    if (firstChartSurfaceMs === null && state.chart_surface_count > 0) {
      firstChartSurfaceMs = elapsed;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
    state = await collectDomState(page);
  }

  const performance = await collectPerformance(page);
  const network = summarizeNetwork(requests, failedRequests);
  const websocketSummary = [...webSockets.values()];
  const firstPartyHttpErrors = [...requests.values()]
    .filter((item) => isFirstParty(item.url) && Number.isFinite(item.status) && item.status >= 400)
    .map((item) => ({ url: item.url, status: item.status, type: item.type }));

  await page.screenshot({
    path: path.join(outputDir, `${profile.id}.png`),
    fullPage: true,
  });

  let verdict;
  if (navigationError) verdict = "EVIDENCE_FAILURE";
  else if ((navigationStatus ?? 0) >= 400 || state.route_error) verdict = "ROUTE_FAILURE";
  else if (!state.useful_ui) verdict = "TERMINAL_NOT_READY";
  else if (
    pageErrors.length > 0 ||
    network.first_party_failed_request_count > 0 ||
    firstPartyHttpErrors.length > 0 ||
    consoleEvents.some((item) => item.type === "error")
  ) {
    verdict = "WARN";
  } else if (state.auth_wall) verdict = "AUTH_WALL_OBSERVED";
  else verdict = "OBSERVED";

  const result = {
    schema_version: "liminalqa-public-terminal-loading-result-v1",
    profile: profile.id,
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    target_url: config.target_url,
    navigation_status: navigationStatus,
    navigation_error: navigationError,
    verdict,
    first_useful_ui_ms: firstUsefulUiMs,
    first_chart_surface_ms: firstChartSurfaceMs,
    dom_state: state,
    performance: {
      ...performance,
      first_contentful_paint_ms: round(performance.first_contentful_paint_ms),
      long_task_total_ms: round(performance.long_task_total_ms),
    },
    network,
    first_party_http_errors: firstPartyHttpErrors,
    console_events: consoleEvents,
    page_errors: pageErrors,
    failed_requests: failedRequests,
    websockets: websocketSummary,
    runtime_profile: profile,
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
    "# LiminalQA · Tradernet public terminal loading",
    "",
    `**Verdict:** ${packet.verdict}  `,
    `**Target:** ${packet.config.target_url}`,
    "",
    "| Profile | HTTP | Result | Useful UI | FCP | LCP | Requests | Transfer | First-party failures | Console errors |",
    "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
  ];
  for (const result of packet.results) {
    const lcp = result.performance.largest_contentful_paint?.startTime;
    const consoleErrors = result.console_events.filter((item) => item.type === "error").length;
    lines.push(
      `| ${result.profile} | ${result.navigation_status ?? "n/a"} | ${result.verdict} | ` +
        `${result.first_useful_ui_ms ?? "n/a"} ms | ` +
        `${result.performance.first_contentful_paint_ms ?? "n/a"} ms | ` +
        `${Number.isFinite(lcp) ? round(lcp) : "n/a"} ms | ` +
        `${result.network.total_requests} | ${result.network.total_encoded_bytes} B | ` +
        `${result.network.first_party_failed_request_count + result.first_party_http_errors.length} | ${consoleErrors} |`
    );
  }
  lines.push("", "## Causal loading path", "", "```text");
  lines.push("Public /terminal navigation");
  lines.push("  → route / redirect / authentication state");
  lines.push("  → document and shared runtime");
  lines.push("  → first useful terminal UI");
  lines.push("  → naturally initiated XHR / fetch / WebSocket activity");
  lines.push("  → first chart or trading surface");
  lines.push("  → errors, failed resources and long tasks");
  lines.push("  → evidence-backed next experiment");
  lines.push("```", "");
  lines.push(
    "> Public passive observation only. The workflow does not authenticate, access a portfolio, call application APIs directly, subscribe to market depth, submit forms, place orders, fuzz endpoints or load test.",
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
  if (config.target_url !== "https://tradernet.ru/terminal") {
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

  const desktop = results.find((item) => item.profile === "desktop_broadband");
  const mobile = results.find((item) => item.profile === "mobile_4g");
  const deviceDivergence = Boolean(
    desktop &&
      mobile &&
      (desktop.navigation_status !== mobile.navigation_status ||
        desktop.dom_state.route_error !== mobile.dom_state.route_error ||
        desktop.dom_state.auth_wall !== mobile.dom_state.auth_wall)
  );
  const verdict = deviceDivergence
    ? "DEVICE_DIVERGENCE"
    : results.some((item) => ["EVIDENCE_FAILURE", "ROUTE_FAILURE", "TERMINAL_NOT_READY", "WARN"].includes(item.verdict))
      ? "WARN"
      : results.every((item) => item.verdict === "AUTH_WALL_OBSERVED")
        ? "AUTH_WALL_OBSERVED"
        : "OBSERVED";

  const packet = {
    schema_version: "liminalqa-public-terminal-loading-packet-v1",
    verdict,
    device_divergence: deviceDivergence,
    config,
    results,
    generated_at: new Date().toISOString(),
  };
  const resultDir = path.join(args["output-dir"], "result");
  await fs.mkdir(resultDir, { recursive: true });
  await fs.writeFile(
    path.join(resultDir, "terminal-loading-result.json"),
    `${JSON.stringify(packet, null, 2)}\n`,
    "utf8"
  );
  await fs.writeFile(
    path.join(resultDir, "terminal-loading-summary.md"),
    renderMarkdown(packet),
    "utf8"
  );
  console.log(JSON.stringify({ verdict, deviceDivergence, profiles: results.map((item) => ({ profile: item.profile, verdict: item.verdict, http: item.navigation_status, useful_ui_ms: item.first_useful_ui_ms })) }, null, 2));
}

main().catch((error) => {
  console.error(normalizeError(error));
  process.exitCode = 1;
});
