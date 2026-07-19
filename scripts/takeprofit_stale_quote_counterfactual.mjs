#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const digest = (value) => crypto.createHash("sha256").update(value).digest("hex");

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

function bodyBytes(body) {
  return body.base64Encoded
    ? Buffer.from(body.body, "base64")
    : Buffer.from(body.body, "utf8");
}

async function dismissCookieBanner(page, timeoutMs = 18000) {
  const deadline = Date.now() + timeoutMs;
  let clicks = 0;
  while (Date.now() < deadline) {
    const clicked = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll("button")];
      const accept = buttons.find((button) => {
        const text = (button.textContent || "").trim().toLowerCase();
        return text === "accept" || text === "accept all" || text === "принять";
      });
      if (!accept) return false;
      accept.click();
      return true;
    });
    if (clicked) {
      clicks += 1;
      await sleep(1000);
    } else {
      await sleep(500);
    }
  }
  return clicks;
}

async function visibleState(page, expectedSymbol) {
  return page.evaluate((symbol) => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rect.width > 2 &&
        rect.height > 2 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0
      );
    };
    const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const lower = text.toLowerCase();
    const terms = [
      "offline",
      "stale",
      "delayed",
      "disconnected",
      "reconnecting",
      "connecting",
      "connection lost",
      "no data",
      "market closed",
      "ошибка соединения",
      "нет соединения",
      "задержка",
      "данные устарели",
    ].filter((term) => lower.includes(term));
    const surfaces = [...document.querySelectorAll("canvas, svg")].filter((element) => {
      if (!visible(element)) return false;
      const rect = element.getBoundingClientRect();
      return rect.width >= 180 && rect.height >= 100;
    });
    return {
      at: new Date().toISOString(),
      url: location.href,
      title: document.title,
      expected_symbol_visible: text.toUpperCase().includes(symbol.toUpperCase()),
      chart_surface_count: surfaces.length,
      freshness_terms: terms,
      text_sample: text.slice(0, 2500),
    };
  }, expectedSymbol);
}

async function screenshot(page, outputDir, filename) {
  const target = path.join(outputDir, filename);
  await page.screenshot({ path: target, fullPage: true });
  const bytes = await fs.readFile(target);
  return { file: filename, sha256: digest(bytes), bytes: bytes.length };
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

async function runVariant(browser, config, outputRoot, variant) {
  const outputDir = path.join(outputRoot, variant);
  await fs.mkdir(outputDir, { recursive: true });

  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport(config.viewport);
  await page.setCacheEnabled(false);

  const cdp = await page.createCDPSession();
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });

  const quoteResponses = [];
  const barResponses = [];
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const bodyTasks = [];
  const samples = [];
  const startedAt = new Date().toISOString();

  let held = null;
  let releasedAt = null;
  let quoteResponseOrdinal = 0;
  const overlappingQuoteResponses = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleErrors.push({ type: message.type(), text: message.text().slice(0, 2000), at: new Date().toISOString() });
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ message: String(error.message || error), stack: String(error.stack || "").slice(0, 3000), at: new Date().toISOString() });
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      method: request.method(),
      resource_type: request.resourceType(),
      error_text: request.failure()?.errorText || null,
      at: new Date().toISOString(),
    });
  });

  if (variant === "treatment") {
    await cdp.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: `*${config.quote_url_fragment}*`,
          requestStage: "Response",
        },
      ],
    });

    cdp.on("Fetch.requestPaused", async (event) => {
      try {
        quoteResponseOrdinal += 1;
        const body = await cdp.send("Fetch.getResponseBody", { requestId: event.requestId });
        const bytes = bodyBytes(body);
        const record = {
          ordinal: quoteResponseOrdinal,
          request_id: event.requestId,
          url: event.request.url,
          response_code: event.responseStatusCode || null,
          received_at_ms: Date.now(),
          received_at: new Date().toISOString(),
          body_sha256: digest(bytes),
          body_bytes: bytes.length,
        };
        quoteResponses.push(record);

        if (quoteResponseOrdinal === config.held_quote_request_number) {
          held = {
            ...record,
            response_headers: event.responseHeaders || [],
            response_phrase: event.responseStatusText || "OK",
            body_base64: bytes.toString("base64"),
            held_at_ms: Date.now(),
            held_at: new Date().toISOString(),
          };
          return;
        }

        if (held && releasedAt === null) {
          overlappingQuoteResponses.push(record);
        }
        await cdp.send("Fetch.continueResponse", { requestId: event.requestId });
      } catch (error) {
        consoleErrors.push({
          type: "probe-error",
          text: `Fetch interception failure: ${String(error?.stack || error).slice(0, 2000)}`,
          at: new Date().toISOString(),
        });
        try {
          await cdp.send("Fetch.continueResponse", { requestId: event.requestId });
        } catch {
          // The request may already have been resolved by Chromium.
        }
      }
    });
  } else {
    page.on("response", (response) => {
      const url = response.url();
      if (!url.includes(config.quote_url_fragment) && !url.includes(config.bars_url_fragment)) return;
      const task = response
        .buffer()
        .then((bytes) => {
          const record = {
            url,
            status: response.status(),
            received_at_ms: Date.now(),
            received_at: new Date().toISOString(),
            body_sha256: digest(bytes),
            body_bytes: bytes.length,
          };
          if (url.includes(config.quote_url_fragment)) quoteResponses.push(record);
          if (url.includes(config.bars_url_fragment)) barResponses.push(record);
        })
        .catch(() => {});
      bodyTasks.push(task);
    });
  }

  if (variant === "treatment") {
    page.on("response", (response) => {
      if (!response.url().includes(config.bars_url_fragment)) return;
      const task = response
        .buffer()
        .then((bytes) => {
          barResponses.push({
            url: response.url(),
            status: response.status(),
            received_at_ms: Date.now(),
            received_at: new Date().toISOString(),
            body_sha256: digest(bytes),
            body_bytes: bytes.length,
          });
        })
        .catch(() => {});
      bodyTasks.push(task);
    });
  }

  const navigation = await page.goto(config.target_url, {
    waitUntil: "domcontentloaded",
    timeout: config.navigation_timeout_ms,
  });
  const cookieClicksTask = dismissCookieBanner(page);

  await waitFor(
    async () => {
      const state = await visibleState(page, config.expected_symbol);
      return state.expected_symbol_visible && state.chart_surface_count > 0 ? state : null;
    },
    config.bootstrap_timeout_ms,
    `${variant} chart bootstrap`,
  );
  await cookieClicksTask;
  const initialState = await visibleState(page, config.expected_symbol);
  const initialShot = await screenshot(page, outputDir, "01-initial.png");

  if (variant === "baseline") {
    await waitFor(() => quoteResponses.length > 0, config.bootstrap_timeout_ms, "baseline first quote response");
    const observationStart = Date.now();
    while (Date.now() - observationStart < config.baseline_observation_ms) {
      samples.push(await visibleState(page, config.expected_symbol));
      await sleep(config.state_sample_interval_ms);
    }
  } else {
    await waitFor(() => held, config.bootstrap_timeout_ms + config.baseline_observation_ms, "held quote response");
    const holdStartState = await visibleState(page, config.expected_symbol);
    const holdStartShot = await screenshot(page, outputDir, "02-hold-start.png");

    while (Date.now() - held.held_at_ms < config.hold_ms) {
      samples.push(await visibleState(page, config.expected_symbol));
      await sleep(config.state_sample_interval_ms);
    }

    const beforeReleaseState = await visibleState(page, config.expected_symbol);
    const beforeReleaseShot = await screenshot(page, outputDir, "03-before-release.png");
    await cdp.send("Fetch.fulfillRequest", {
      requestId: held.request_id,
      responseCode: held.response_code || 200,
      responsePhrase: held.response_phrase,
      responseHeaders: held.response_headers,
      body: held.body_base64,
    });
    releasedAt = Date.now();

    const postDeadline = Date.now() + config.post_release_observation_ms;
    while (Date.now() < postDeadline) {
      samples.push(await visibleState(page, config.expected_symbol));
      await sleep(config.state_sample_interval_ms);
    }
    const afterReleaseState = await visibleState(page, config.expected_symbol);
    const afterReleaseShot = await screenshot(page, outputDir, "04-after-release.png");

    held.hold_duration_ms = releasedAt - held.held_at_ms;
    held.released_at_ms = releasedAt;
    held.released_at = new Date(releasedAt).toISOString();
    held.delivered_after_newer_response = overlappingQuoteResponses.some(
      (item) => item.received_at_ms < releasedAt,
    );
    held.states = { hold_start: holdStartState, before_release: beforeReleaseState, after_release: afterReleaseState };
    held.screenshots = { hold_start: holdStartShot, before_release: beforeReleaseShot, after_release: afterReleaseShot };
  }

  await Promise.allSettled(bodyTasks);
  const finalState = await visibleState(page, config.expected_symbol);
  const finalShot = await screenshot(page, outputDir, "05-final.png");

  const distinctQuoteBodies = [...new Set(quoteResponses.map((item) => item.body_sha256))];
  const sampleFreshnessTerms = [...new Set(samples.flatMap((sample) => sample.freshness_terms))];
  const quoteGapsMs = quoteResponses
    .slice(1)
    .map((item, index) => item.received_at_ms - quoteResponses[index].received_at_ms);

  const result = {
    variant,
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    navigation_status: navigation?.status() ?? null,
    final_url: page.url(),
    cookie_accept_clicks: await cookieClicksTask,
    initial_state: initialState,
    final_state: finalState,
    quote_response_count: quoteResponses.length,
    distinct_quote_body_count: distinctQuoteBodies.length,
    quote_body_hashes: distinctQuoteBodies,
    quote_response_gaps_ms: quoteGapsMs,
    quote_responses: quoteResponses.map(({ request_id, ...item }) => item),
    bar_response_count: barResponses.length,
    bar_responses: barResponses,
    freshness_terms_observed: sampleFreshnessTerms,
    sample_count: samples.length,
    held_response: held
      ? {
          ordinal: held.ordinal,
          body_sha256: held.body_sha256,
          body_bytes: held.body_bytes,
          held_at: held.held_at,
          released_at: held.released_at,
          hold_duration_ms: held.hold_duration_ms,
          delivered_after_newer_response: held.delivered_after_newer_response,
          states: held.states,
          screenshots: held.screenshots,
        }
      : null,
    overlapping_quote_responses: overlappingQuoteResponses.map(({ request_id, ...item }) => item),
    console_errors: consoleErrors,
    page_errors: pageErrors,
    failed_requests: failedRequests,
    screenshots: { initial: initialShot, final: finalShot },
  };

  await fs.writeFile(path.join(outputDir, "result.json"), `${JSON.stringify(result, null, 2)}\n`);
  await context.close();
  return result;
}

function classify(config, baseline, treatment) {
  const holdAchieved = Boolean(treatment.held_response);
  const chartVisibleDuringHold = Boolean(
    treatment.held_response?.states?.before_release?.chart_surface_count > 0 &&
      treatment.held_response?.states?.before_release?.expected_symbol_visible,
  );
  const freshnessBoundaryVisible = treatment.freshness_terms_observed.some((term) =>
    ["offline", "stale", "delayed", "disconnected", "reconnecting", "connection lost", "ошибка соединения", "нет соединения", "задержка", "данные устарели"].includes(term),
  );
  const recoveryVisible = Boolean(
    treatment.final_state.chart_surface_count > 0 && treatment.final_state.expected_symbol_visible,
  );
  const naturalOverlap = treatment.overlapping_quote_responses.length > 0;
  const outOfOrderDeliveryCreated = Boolean(
    treatment.held_response?.delivered_after_newer_response,
  );

  const checks = {
    baseline_quote_liveness:
      baseline.quote_response_count >= 2 && baseline.distinct_quote_body_count >= 2 ? "PASS" : "WARN",
    hold_experiment: holdAchieved ? "PASS" : "INCONCLUSIVE",
    stale_state_clarity:
      holdAchieved && chartVisibleDuringHold ? (freshnessBoundaryVisible ? "PASS" : "FAIL") : "INCONCLUSIVE",
    recovery_after_release: holdAchieved ? (recoveryVisible ? "PASS" : "FAIL") : "INCONCLUSIVE",
    natural_poll_overlap: naturalOverlap ? "OBSERVED" : "NOT_OBSERVED",
    out_of_order_transport_delivery: outOfOrderDeliveryCreated ? "CREATED" : "NOT_CREATED",
    out_of_order_application_effect: outOfOrderDeliveryCreated ? "UNVERIFIED" : "NOT_TESTED",
  };

  let verdict = "PASS";
  if (checks.hold_experiment === "INCONCLUSIVE") verdict = "INCONCLUSIVE";
  else if (checks.stale_state_clarity === "FAIL") verdict = "SUPPORTED_STALE_STATE_GAP";
  else if (Object.values(checks).includes("WARN")) verdict = "WARN";

  return {
    verdict,
    checks,
    interpretation: {
      stale_state_gap_confirmed:
        checks.stale_state_clarity === "FAIL",
      polling_model:
        naturalOverlap
          ? "The client initiated another quote response while an older response was held."
          : "No natural overlapping quote response was observed while the older response was held; polling may be serialized or the observation window may be insufficient.",
      ordering_boundary:
        outOfOrderDeliveryCreated
          ? "An older browser-held quote response was delivered after a newer response, but whether the application applied or rejected it is not observable from the public canvas and remains unverified."
          : "No older-after-newer transport delivery was created; application ordering remains untested.",
      pythia_boundary:
        "Confirmed observations remain separate from application-state hypotheses. Missing canvas-level quote identity prevents a claim that the visible price rolled back.",
      cml_boundary:
        "The result may be linked to the earlier five-second interruption and ChartStore initialization family as correlated evidence, not as a confirmed shared root cause.",
      ls_boundary:
        "A visible last-known chart without a freshness marker reduces the user's ability to distinguish current market state from retained state.",
    },
  };
}

function renderMarkdown(config, baseline, treatment, classification, evidenceHash) {
  const held = treatment.held_response;
  const rows = Object.entries(classification.checks)
    .map(([name, verdict]) => `| ${name} | ${verdict} |`)
    .join("\n");
  return `# LiminalQA · TakeProfit stale quote counterfactual\n\n**Target:** \`${config.target_url}\`  \n**Verdict:** **${classification.verdict}**  \n**Evidence SHA-256:** \`${evidenceHash}\`\n\n## Decision matrix\n\n| Check | Verdict |\n|---|---|\n${rows}\n\n## Baseline\n\n- Quote responses: **${baseline.quote_response_count}**\n- Distinct quote bodies: **${baseline.distinct_quote_body_count}**\n- Observed response gaps: **${baseline.quote_response_gaps_ms.join(", ") || "n/a"} ms**\n- Freshness terms shown: **${baseline.freshness_terms_observed.join(", ") || "none"}**\n\n## Treatment\n\n- Held quote response: **${held ? `#${held.ordinal}` : "not achieved"}**\n- Hold duration: **${held?.hold_duration_ms ?? "n/a"} ms**\n- Chart and BTC/USDT remained visible before release: **${held ? held.states.before_release.chart_surface_count > 0 && held.states.before_release.expected_symbol_visible : false}**\n- Freshness terms during treatment: **${treatment.freshness_terms_observed.join(", ") || "none"}**\n- Newer quote responses while old response was held: **${treatment.overlapping_quote_responses.length}**\n- Older response delivered after a newer response: **${held?.delivered_after_newer_response ?? false}**\n- Chart visible after release: **${treatment.final_state.chart_surface_count > 0 && treatment.final_state.expected_symbol_visible}**\n\n## Lotus reading\n\n### Pythia\n\nThe delayed-response and UI observations are evidence. A visible-price rollback is **not** claimed because the canvas does not expose symbol-bound quote identity. Application ordering remains explicit uncertainty.\n\n### CML\n\nThis run can be linked to the prior five-second interruption and the historical ChartStore initialization family. Repetition supports a recurring state/freshness pattern; it does not by itself prove one shared root cause.\n\n### LS\n\nWhen the last-known market chart remains plausible beyond the expected refresh boundary without a stale or delayed marker, the user loses informed control over whether the displayed state is current.\n\n## Boundaries\n\nThe workflow delays only one response naturally initiated by the public page. It does not authenticate, call the endpoint directly, place trades, fuzz, load test, mutate server state, or claim a security vulnerability.\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  if (config.target_url !== "https://takeprofit.com/indicator/atr-super-trend-multi-source-57") {
    throw new Error("Unexpected target URL");
  }
  if (config.hold_ms > 90000 || config.baseline_observation_ms > 90000) {
    throw new Error("Counterfactual duration exceeds the bounded policy");
  }

  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
    ],
  });

  let baseline;
  let treatment;
  try {
    baseline = await runVariant(browser, config, args["output-dir"], "baseline");
    treatment = await runVariant(browser, config, args["output-dir"], "treatment");
  } finally {
    await browser.close();
  }

  const classification = classify(config, baseline, treatment);
  const packet = {
    schema_version: "liminalqa-takeprofit-stale-quote-counterfactual-result-v1",
    target: config.target_url,
    generated_at: new Date().toISOString(),
    config,
    baseline,
    treatment,
    classification,
    boundaries: config.boundaries,
  };
  const resultBytes = Buffer.from(`${JSON.stringify(packet, null, 2)}\n`);
  const evidenceHash = digest(resultBytes);
  packet.evidence_sha256 = evidenceHash;

  const finalBytes = Buffer.from(`${JSON.stringify(packet, null, 2)}\n`);
  await fs.writeFile(path.join(args["output-dir"], "stale-quote-result.json"), finalBytes);
  await fs.writeFile(
    path.join(args["output-dir"], "stale-quote-summary.md"),
    renderMarkdown(config, baseline, treatment, classification, evidenceHash),
  );
  console.log(JSON.stringify({ verdict: classification.verdict, checks: classification.checks, evidence_sha256: evidenceHash }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
