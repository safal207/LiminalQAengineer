#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

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

async function dismissCookieBanner(page, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  let clicks = 0;
  while (Date.now() < deadline) {
    const clicked = await page.evaluate(() => {
      const accept = [...document.querySelectorAll("button")].find((button) => {
        const text = (button.textContent || "").trim().toLowerCase();
        return ["accept", "accept all", "принять"].includes(text);
      });
      if (!accept) return false;
      accept.click();
      return true;
    });
    if (clicked) clicks += 1;
    await sleep(clicked ? 700 : 350);
  }
  return clicks;
}

async function visibleState(page, expectedSymbol) {
  return page.evaluate((symbol) => {
    const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const lower = text.toLowerCase();
    const vocabulary = [
      "offline",
      "stale",
      "delayed",
      "disconnected",
      "reconnecting",
      "connecting",
      "connection lost",
      "no data",
      "ошибка соединения",
      "нет соединения",
      "задержка",
      "данные устарели",
    ];
    const freshnessTerms = vocabulary.filter((term) => lower.includes(term));
    const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const contexts = [];
    const symbolRegex = new RegExp(escaped, "gi");
    let match;
    while ((match = symbolRegex.exec(text)) && contexts.length < 8) {
      contexts.push(text.slice(match.index, Math.min(text.length, match.index + 160)));
    }
    const priceCandidates = contexts
      .flatMap((context) => [...context.matchAll(/\b\d{2,8}(?:[.,]\d+)?\b/g)].map((item) => Number(item[0].replace(",", "."))))
      .filter((value) => Number.isFinite(value) && value >= 100 && value <= 100_000_000);
    const surfaces = [...document.querySelectorAll("canvas, svg")].filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width >= 180 && rect.height >= 100 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
    });
    return {
      at_ms: Date.now(),
      at: new Date().toISOString(),
      url: location.href,
      title: document.title,
      expected_symbol_visible: text.toUpperCase().includes(symbol.toUpperCase()),
      chart_surface_count: surfaces.length,
      freshness_terms: freshnessTerms,
      symbol_contexts: contexts,
      visible_price_candidates: [...new Set(priceCandidates)].slice(0, 20),
      primary_visible_price: priceCandidates[0] ?? null,
      text_sample: text.slice(0, 3000),
    };
  }, expectedSymbol);
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

async function screenshot(page, directory, filename) {
  const target = path.join(directory, filename);
  await page.screenshot({ path: target, fullPage: true });
  const bytes = await fs.readFile(target);
  return { file: filename, bytes: bytes.length, sha256: sha256(bytes) };
}

async function setOffline(cdp, offline) {
  await cdp.send("Network.emulateNetworkConditions", {
    offline,
    latency: 0,
    downloadThroughput: offline ? 0 : -1,
    uploadThroughput: offline ? 0 : -1,
    connectionType: offline ? "none" : "wifi",
  });
}

function classifyRound(round) {
  const markerTerms = [...new Set(round.outage_samples.flatMap((sample) => sample.freshness_terms))];
  const chartVisible = round.before_restore_state.expected_symbol_visible && round.before_restore_state.chart_surface_count > 0;
  const noQuoteDuringOutage = round.quote_responses_during_outage === 0;
  const outageAchieved = round.actual_outage_ms >= round.requested_outage_ms && noQuoteDuringOutage;
  const recovered = Boolean(round.recovery_quote_response) && round.final_state.expected_symbol_visible && round.final_state.chart_surface_count > 0;
  return {
    network_outage: outageAchieved ? "PASS" : "INCONCLUSIVE",
    retained_chart_during_outage: chartVisible ? "OBSERVED" : "NOT_OBSERVED",
    freshness_boundary: outageAchieved && chartVisible ? (markerTerms.length ? "VISIBLE" : "MISSING") : "INCONCLUSIVE",
    recovery_after_restore: recovered ? "PASS" : "FAIL",
    evidence: {
      quote_responses_during_outage: round.quote_responses_during_outage,
      freshness_terms: markerTerms,
      visible_price_before_outage: round.before_outage_state.primary_visible_price,
      visible_price_before_restore: round.before_restore_state.primary_visible_price,
      visible_price_after_recovery: round.final_state.primary_visible_price,
    },
  };
}

async function runRound(browser, config, outputRoot, roundIndex, outageMs) {
  const directory = path.join(outputRoot, `round-${roundIndex + 1}-${outageMs}ms`);
  await fs.mkdir(directory, { recursive: true });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport(config.viewport);
  await page.setCacheEnabled(false);
  const cdp = await page.createCDPSession();
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });

  const quoteResponses = [];
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const bodyTasks = [];
  let outageStartedAtMs = null;
  let restoredAtMs = null;

  page.on("response", (response) => {
    if (!response.url().includes(config.quote_url_fragment)) return;
    const task = response.buffer().then((bytes) => {
      quoteResponses.push({
        received_at_ms: Date.now(),
        received_at: new Date().toISOString(),
        url: response.url(),
        status: response.status(),
        body_bytes: bytes.length,
        body_sha256: sha256(bytes),
      });
    }).catch(() => {});
    bodyTasks.push(task);
  });
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) consoleErrors.push({ type: message.type(), text: message.text().slice(0, 2000), at: new Date().toISOString() });
  });
  page.on("pageerror", (error) => pageErrors.push({ message: String(error.message || error), at: new Date().toISOString() }));
  page.on("requestfailed", (request) => failedRequests.push({
    url: request.url(),
    method: request.method(),
    resource_type: request.resourceType(),
    error_text: request.failure()?.errorText || null,
    at_ms: Date.now(),
    at: new Date().toISOString(),
  }));

  const navigation = await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: config.navigation_timeout_ms });
  const cookieTask = dismissCookieBanner(page);
  await waitFor(() => quoteResponses.some((item) => item.body_bytes > 0), config.bootstrap_timeout_ms, "initial non-empty quote response");
  await waitFor(async () => {
    const state = await visibleState(page, config.expected_symbol);
    return state.expected_symbol_visible && state.chart_surface_count > 0 ? state : null;
  }, config.bootstrap_timeout_ms, "public chart and symbol visibility");
  await cookieTask;
  await Promise.allSettled(bodyTasks);

  const beforeOutageState = await visibleState(page, config.expected_symbol);
  const beforeOutageScreenshot = await screenshot(page, directory, "01-before-outage.png");
  const responseCountBeforeOutage = quoteResponses.length;
  outageStartedAtMs = Date.now();
  await setOffline(cdp, true);

  const outageSamples = [];
  while (Date.now() - outageStartedAtMs < outageMs) {
    outageSamples.push(await visibleState(page, config.expected_symbol));
    await sleep(config.outage_sample_interval_ms);
  }
  const beforeRestoreState = await visibleState(page, config.expected_symbol);
  const beforeRestoreScreenshot = await screenshot(page, directory, "02-before-restore.png");
  const actualOutageMs = Date.now() - outageStartedAtMs;
  const responseCountBeforeRestore = quoteResponses.length;

  restoredAtMs = Date.now();
  await setOffline(cdp, false);
  const recoveryQuoteResponse = await waitFor(
    () => quoteResponses.find((item) => item.received_at_ms > restoredAtMs && item.body_bytes > 0),
    config.recovery_timeout_ms,
    "post-restore non-empty quote response",
  );

  const recoverySamples = [];
  const recoveryDeadline = Date.now() + config.post_restore_observation_ms;
  while (Date.now() < recoveryDeadline) {
    recoverySamples.push(await visibleState(page, config.expected_symbol));
    await sleep(config.post_restore_sample_interval_ms);
  }
  await Promise.allSettled(bodyTasks);
  const finalState = await visibleState(page, config.expected_symbol);
  const afterRestoreScreenshot = await screenshot(page, directory, "03-after-restore.png");

  const round = {
    round: roundIndex + 1,
    requested_outage_ms: outageMs,
    actual_outage_ms: actualOutageMs,
    navigation_status: navigation?.status() ?? null,
    final_url: page.url(),
    cookie_accept_clicks: await cookieTask,
    before_outage_state: beforeOutageState,
    before_restore_state: beforeRestoreState,
    final_state: finalState,
    outage_samples: outageSamples,
    recovery_samples: recoverySamples,
    quote_responses: quoteResponses,
    quote_responses_during_outage: responseCountBeforeRestore - responseCountBeforeOutage,
    recovery_quote_response: recoveryQuoteResponse,
    failed_requests_during_outage: failedRequests.filter((item) => item.at_ms >= outageStartedAtMs && item.at_ms < restoredAtMs),
    screenshots: { before_outage: beforeOutageScreenshot, before_restore: beforeRestoreScreenshot, after_restore: afterRestoreScreenshot },
    console_errors: consoleErrors,
    page_errors: pageErrors,
    failed_requests: failedRequests,
  };
  round.classification = classifyRound(round);
  await fs.writeFile(path.join(directory, "round-result.json"), `${JSON.stringify(round, null, 2)}\n`);
  await context.close();
  return round;
}

function classifyPacket(rounds) {
  const missing = rounds.filter((round) => round.classification.freshness_boundary === "MISSING");
  const visible = rounds.filter((round) => round.classification.freshness_boundary === "VISIBLE");
  const outagePass = rounds.filter((round) => round.classification.network_outage === "PASS");
  const recoveryPass = rounds.filter((round) => round.classification.recovery_after_restore === "PASS");
  let verdict = "INCONCLUSIVE";
  if (outagePass.length === 3 && missing.length === 3 && recoveryPass.length === 3) verdict = "CONFIRMED_MISSING_FRESHNESS_BOUNDARY_DURING_OUTAGE";
  else if (missing.length >= 2) verdict = "SUPPORTED_MISSING_FRESHNESS_BOUNDARY_DURING_OUTAGE";
  else if (visible.length === 3) verdict = "PASS";
  return {
    verdict,
    checks: {
      three_independent_rounds: rounds.length === 3 ? "PASS" : "FAIL",
      cadence_exceeding_network_outages: outagePass.length === 3 ? "PASS" : `${outagePass.length}_OF_3`,
      retained_chart_without_freshness_marker: missing.length === 3 ? "CONFIRMED_ALL_ROUNDS" : `${missing.length}_OF_3`,
      recovery_after_network_restore: recoveryPass.length === 3 ? "PASS" : `${recoveryPass.length}_OF_3`,
      visible_price_accuracy_against_market: "NOT_TESTED",
      authenticated_workspace_behavior: "NOT_TESTED",
    },
    counts: { rounds: rounds.length, outage_pass: outagePass.length, freshness_missing: missing.length, freshness_visible: visible.length, recovery_pass: recoveryPass.length },
    pythia_boundary: "This experiment can confirm whether a visible public chart exposes a freshness boundary during a real browser-level network outage. It does not prove the displayed price was wrong relative to an external market source.",
    cml_boundary: "Three independent outage repetitions may establish a recurring public freshness-signaling defect family; they do not establish one root cause with ChartStore initialization or authenticated workspace transport.",
    ls_boundary: "When a BTC/USDT chart and price remain plausible during a prolonged network outage without an explicit stale/offline state, the user cannot reliably distinguish retained state from current state.",
  };
}

function renderMarkdown(packet) {
  const rows = packet.rounds.map((round) => `| ${round.round} | ${round.requested_outage_ms} | ${round.actual_outage_ms} | ${round.classification.network_outage} | ${round.classification.retained_chart_during_outage} | ${round.classification.freshness_boundary} | ${round.classification.recovery_after_restore} |`).join("\n");
  return `# TakeProfit public quote freshness outage v2\n\n**Target:** \`${packet.target}\`  \n**Verdict:** **${packet.classification.verdict}**  \n**Evidence SHA-256:** \`${packet.evidence_sha256}\`\n\n## Three-round matrix\n\n| Round | Requested outage ms | Actual outage ms | Outage | Chart retained | Freshness boundary | Recovery |\n|---:|---:|---:|---|---|---|---|\n${rows}\n\n## Aggregate checks\n\n- Three independent rounds: **${packet.classification.checks.three_independent_rounds}**\n- Cadence-exceeding outages: **${packet.classification.checks.cadence_exceeding_network_outages}**\n- Retained chart without freshness marker: **${packet.classification.checks.retained_chart_without_freshness_marker}**\n- Recovery after restore: **${packet.classification.checks.recovery_after_network_restore}**\n- Visible price accuracy against an external market source: **NOT TESTED**\n- Authenticated workspace behavior: **NOT TESTED**\n\n## Lotus reading\n\n### Pythia\n\n${packet.classification.pythia_boundary}\n\n### CML\n\n${packet.classification.cml_boundary}\n\n### LS\n\n${packet.classification.ls_boundary}\n\n## Boundary\n\nThe workflow observes one allowlisted public page and uses Chrome's browser-level offline mode after a naturally initiated quote response. It does not authenticate, call the quote endpoint directly, mutate TakeProfit server state, place financial operations, fuzz, load test, exploit, or claim a security vulnerability.\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) if (!args[key]) throw new Error(`--${key} is required`);
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  if (config.target_url !== "https://takeprofit.com/indicator/atr-super-trend-multi-source-57") throw new Error("Unexpected target URL");
  if (JSON.stringify(config.outage_durations_ms) !== JSON.stringify([90000, 105000, 120000])) throw new Error("The exact three cadence-aware outage durations are required");
  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({ executablePath: args.chrome, headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-timer-throttling", "--disable-renderer-backgrounding"] });
  const rounds = [];
  try {
    for (let index = 0; index < config.outage_durations_ms.length; index += 1) rounds.push(await runRound(browser, config, args["output-dir"], index, config.outage_durations_ms[index]));
  } finally {
    await browser.close();
  }
  const packet = {
    schema_version: "liminalqa-takeprofit-quote-freshness-outage-result-v2",
    generated_at: new Date().toISOString(),
    target: config.target_url,
    config,
    rounds,
    classification: classifyPacket(rounds),
    boundaries: config.boundaries,
    authority: { mode: "evidence_only", grants: { ownership: false, approval: false, execution: false, delivery: false, deployment: false, merge: false } },
  };
  packet.evidence_sha256 = sha256(Buffer.from(`${JSON.stringify(packet, null, 2)}\n`));
  await fs.writeFile(path.join(args["output-dir"], "quote-freshness-outage-result.json"), `${JSON.stringify(packet, null, 2)}\n`);
  await fs.writeFile(path.join(args["output-dir"], "quote-freshness-outage-summary.md"), renderMarkdown(packet));
  console.log(JSON.stringify({ verdict: packet.classification.verdict, checks: packet.classification.checks, evidence_sha256: packet.evidence_sha256 }, null, 2));
}

main().catch((error) => { console.error(error?.stack || error); process.exitCode = 1; });
