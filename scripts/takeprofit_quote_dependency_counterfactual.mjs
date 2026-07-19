#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";
import { PNG } from "pngjs";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    args[key.slice(2)] = value;
  }
  return args;
}

async function waitFor(predicate, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await predicate();
    if (value) return value;
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function dismissCookieBanner(page, timeoutMs = 18000) {
  const deadline = Date.now() + timeoutMs;
  let clicks = 0;
  while (Date.now() < deadline) {
    const clicked = await page.evaluate(() => {
      const button = [...document.querySelectorAll("button")].find((item) => {
        const text = (item.textContent || "").trim().toLowerCase();
        return text === "accept" || text === "accept all" || text === "принять";
      });
      if (!button) return false;
      button.click();
      return true;
    });
    if (clicked) {
      clicks += 1;
      await sleep(750);
    } else {
      await sleep(400);
    }
  }
  return clicks;
}

async function visibleState(page, expectedSymbol) {
  return page.evaluate((symbol) => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 2 && rect.height > 2 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
    };
    const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const lower = text.toLowerCase();
    const freshnessTerms = [
      "offline",
      "stale",
      "delayed",
      "disconnected",
      "reconnecting",
      "connection lost",
      "no data",
      "ошибка соединения",
      "нет соединения",
      "задержка",
      "данные устарели",
    ].filter((term) => lower.includes(term));
    const rects = [...document.querySelectorAll("canvas")]
      .filter(visible)
      .map((canvas) => {
        const rect = canvas.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, area: rect.width * rect.height };
      })
      .filter((rect) => rect.width >= 180 && rect.height >= 100)
      .sort((a, b) => b.area - a.area);
    return {
      at: new Date().toISOString(),
      expected_symbol_visible: text.toUpperCase().includes(symbol.toUpperCase()),
      freshness_terms: freshnessTerms,
      chart_rect: rects[0] || null,
      body_text_sha256_source: text,
      text_sample: text.slice(0, 1800),
    };
  }, expectedSymbol);
}

function clipFrom(rect, viewport) {
  if (!rect) throw new Error("No chart canvas found");
  const x = Math.max(0, Math.floor(rect.x));
  const y = Math.max(0, Math.floor(rect.y));
  return {
    x,
    y,
    width: Math.max(1, Math.min(Math.ceil(rect.width), viewport.width - x)),
    height: Math.max(1, Math.min(Math.ceil(rect.height), viewport.height - y)),
  };
}

async function screenshotCrop(page, outputDir, label, clip) {
  const file = `${label}.png`;
  const target = path.join(outputDir, file);
  await page.screenshot({ path: target, clip, captureBeyondViewport: false });
  const bytes = await fs.readFile(target);
  return { file, bytes: bytes.length, sha256: sha256(bytes) };
}

function imageDifference(leftBytes, rightBytes, channelThreshold) {
  const left = PNG.sync.read(leftBytes);
  const right = PNG.sync.read(rightBytes);
  if (left.width !== right.width || left.height !== right.height) return { comparable: false, changed_ratio: null, changed_pixels: null };
  let changed = 0;
  const pixels = left.width * left.height;
  for (let index = 0; index < left.data.length; index += 4) {
    const delta = Math.max(
      Math.abs(left.data[index] - right.data[index]),
      Math.abs(left.data[index + 1] - right.data[index + 1]),
      Math.abs(left.data[index + 2] - right.data[index + 2]),
      Math.abs(left.data[index + 3] - right.data[index + 3]),
    );
    if (delta > channelThreshold) changed += 1;
  }
  return { comparable: true, changed_pixels: changed, changed_ratio: changed / pixels };
}

async function runVariant(browser, config, outputRoot, pair, variant) {
  const outputDir = path.join(outputRoot, `pair-${pair}-${variant}`);
  await fs.mkdir(outputDir, { recursive: true });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport(config.viewport);
  await page.setCacheEnabled(false);

  const quoteResponses = [];
  const blockedQuoteRequests = [];
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const responseTasks = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleErrors.push({ type: message.type(), text: message.text().slice(0, 1800), at: new Date().toISOString() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push({ message: String(error.message || error), at: new Date().toISOString() }));
  page.on("requestfailed", (request) => {
    failedRequests.push({ url: request.url(), error_text: request.failure()?.errorText || null, at: new Date().toISOString() });
  });
  page.on("response", (response) => {
    if (!response.url().includes(config.quote_url_fragment)) return;
    const task = response
      .buffer()
      .then((bytes) => quoteResponses.push({ status: response.status(), bytes: bytes.length, sha256: sha256(bytes), at: new Date().toISOString() }))
      .catch(() => {});
    responseTasks.push(task);
  });

  if (variant === "treatment") {
    const cdp = await page.createCDPSession();
    await cdp.send("Fetch.enable", {
      patterns: [{ urlPattern: `*${config.quote_url_fragment}*`, requestStage: "Request" }],
    });
    cdp.on("Fetch.requestPaused", async (event) => {
      blockedQuoteRequests.push({ url: event.request.url, at: new Date().toISOString() });
      await cdp.send("Fetch.failRequest", { requestId: event.requestId, errorReason: "BlockedByClient" });
    });
  }

  const navigation = await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: config.navigation_timeout_ms });
  const cookieTask = dismissCookieBanner(page);
  const initial = await waitFor(
    async () => {
      const state = await visibleState(page, config.expected_symbol);
      return state.expected_symbol_visible && state.chart_rect ? state : null;
    },
    config.bootstrap_timeout_ms,
    `${variant} chart bootstrap`,
  );
  await cookieTask;
  const clip = clipFrom(initial.chart_rect, config.viewport);
  const initialShot = await screenshotCrop(page, outputDir, "01-initial-chart", clip);
  await sleep(config.observation_ms);
  await Promise.allSettled(responseTasks);
  const final = await visibleState(page, config.expected_symbol);
  const finalShot = await screenshotCrop(page, outputDir, "02-final-chart", clip);

  const result = {
    pair,
    variant,
    navigation_status: navigation?.status() ?? null,
    final_url: page.url(),
    cookie_accept_clicks: await cookieTask,
    quote_response_count: quoteResponses.length,
    quote_responses: quoteResponses,
    blocked_quote_request_count: blockedQuoteRequests.length,
    blocked_quote_requests: blockedQuoteRequests,
    initial_state: { ...initial, body_text_sha256: sha256(Buffer.from(initial.body_text_sha256_source)) },
    final_state: { ...final, body_text_sha256: sha256(Buffer.from(final.body_text_sha256_source)) },
    screenshots: { initial: initialShot, final: finalShot },
    console_errors: consoleErrors,
    page_errors: pageErrors,
    failed_requests: failedRequests,
  };
  delete result.initial_state.body_text_sha256_source;
  delete result.final_state.body_text_sha256_source;
  await fs.writeFile(path.join(outputDir, "result.json"), `${JSON.stringify(result, null, 2)}\n`);
  await context.close();
  return result;
}

async function comparePair(outputRoot, pair, baseline, treatment, config) {
  const baselineBytes = await fs.readFile(path.join(outputRoot, `pair-${pair}-baseline`, baseline.screenshots.final.file));
  const treatmentBytes = await fs.readFile(path.join(outputRoot, `pair-${pair}-treatment`, treatment.screenshots.final.file));
  const diff = imageDifference(baselineBytes, treatmentBytes, config.visual_threshold.channel_delta);
  const chartVisible = Boolean(treatment.final_state.expected_symbol_visible && treatment.final_state.chart_rect);
  const freshnessAbsent = treatment.final_state.freshness_terms.length === 0;
  const bodyTextSame = baseline.final_state.body_text_sha256 === treatment.final_state.body_text_sha256;
  return {
    pair,
    baseline_quote_responses: baseline.quote_response_count,
    treatment_blocked_quote_requests: treatment.blocked_quote_request_count,
    treatment_chart_visible: chartVisible,
    treatment_freshness_terms: treatment.final_state.freshness_terms,
    body_text_same: bodyTextSame,
    chart_difference: diff,
    no_material_visible_difference:
      chartVisible && freshnessAbsent && bodyTextSame && diff.comparable && diff.changed_ratio <= config.visual_threshold.changed_ratio,
    baseline_chart_sha256: baseline.screenshots.final.sha256,
    treatment_chart_sha256: treatment.screenshots.final.sha256,
    baseline_console_errors: baseline.console_errors.map((item) => item.text),
    treatment_console_errors: treatment.console_errors.map((item) => item.text),
  };
}

function classify(pairs) {
  const supportedPairs = pairs.filter(
    (pair) => pair.baseline_quote_responses > 0 && pair.treatment_blocked_quote_requests > 0 && pair.no_material_visible_difference,
  ).length;
  const visibleDependencyPairs = pairs.filter(
    (pair) => pair.treatment_chart_visible && !pair.no_material_visible_difference,
  ).length;
  let verdict = "INCONCLUSIVE";
  if (supportedPairs >= 2) verdict = "SUPPORTED_NO_VISIBLE_INITIAL_QUOTE_DEPENDENCY";
  else if (visibleDependencyPairs >= 2) verdict = "VISIBLE_QUOTE_DEPENDENCY_OBSERVED";
  return {
    verdict,
    supported_pairs: supportedPairs,
    visible_dependency_pairs: visibleDependencyPairs,
    pythia_boundary:
      verdict === "SUPPORTED_NO_VISIBLE_INITIAL_QUOTE_DEPENDENCY"
        ? "Blocking naturally initiated quote requests did not materially change the initial visible chart in at least two paired runs. This supports no visible initial dependency, not universal unused-code or endpoint claims."
        : "The paired evidence is insufficient to classify the quote request as visibly unnecessary or visibly required.",
    cml_boundary:
      "This result may refine the static-chart and quote-polling memory, but it does not establish why the page requests current quotes.",
    ls_boundary:
      "If the chart is intentionally historical, an explicit snapshot or as-of label is a clearer user-control fix than relying on invisible transport behavior.",
  };
}

function renderMarkdown(config, pairs, classification, evidenceHash) {
  const rows = pairs
    .map((pair) => `| ${pair.pair} | ${pair.baseline_quote_responses} | ${pair.treatment_blocked_quote_requests} | ${pair.treatment_chart_visible} | ${pair.chart_difference.changed_ratio ?? "n/a"} | ${pair.body_text_same} | ${pair.no_material_visible_difference} |`)
    .join("\n");
  return `# LiminalQA · TakeProfit quote visible-dependency counterfactual\n\n**Target:** \`${config.target_url}\`  \n**Verdict:** **${classification.verdict}**  \n**Evidence SHA-256:** \`${evidenceHash}\`\n\n| Pair | Baseline quote responses | Blocked in treatment | Chart visible | Chart diff ratio | Body text same | No material visible difference |\n|---:|---:|---:|---|---:|---|---|\n${rows}\n\n## Pythia\n\n${classification.pythia_boundary}\n\n## CML\n\n${classification.cml_boundary}\n\n## LS\n\n${classification.ls_boundary}\n\n## Boundary\n\nThe treatment blocks only quote requests naturally initiated by one public page. It does not call the endpoint directly, authenticate, access account data, submit financial operations, fuzz, load test, exploit, or claim a security vulnerability.\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) if (!args[key]) throw new Error(`--${key} is required`);
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  if (config.target_url !== "https://takeprofit.com/indicator/atr-super-trend-multi-source-57" || config.pairs !== 3) {
    throw new Error("Unexpected target or pair count");
  }
  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-timer-throttling", "--disable-renderer-backgrounding"],
  });
  const runs = [];
  const pairs = [];
  try {
    for (let pair = 1; pair <= config.pairs; pair += 1) {
      const baseline = await runVariant(browser, config, args["output-dir"], pair, "baseline");
      const treatment = await runVariant(browser, config, args["output-dir"], pair, "treatment");
      runs.push(baseline, treatment);
      pairs.push(await comparePair(args["output-dir"], pair, baseline, treatment, config));
    }
  } finally {
    await browser.close();
  }
  const classification = classify(pairs);
  const packet = {
    schema_version: "liminalqa-takeprofit-quote-visible-dependency-result-v1",
    generated_at: new Date().toISOString(),
    target: config.target_url,
    config,
    runs,
    pairs,
    classification,
    boundaries: config.boundaries,
  };
  const evidenceHash = sha256(Buffer.from(JSON.stringify(packet)));
  packet.evidence_sha256 = evidenceHash;
  await fs.writeFile(path.join(args["output-dir"], "quote-visible-dependency-result.json"), `${JSON.stringify(packet, null, 2)}\n`);
  await fs.writeFile(path.join(args["output-dir"], "quote-visible-dependency-summary.md"), renderMarkdown(config, pairs, classification, evidenceHash));
  console.log(JSON.stringify({ classification, evidence_sha256: evidenceHash }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
