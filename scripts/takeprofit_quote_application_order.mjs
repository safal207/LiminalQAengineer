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

async function installCanvasProbe(page) {
  await page.evaluateOnNewDocument(() => {
    const root = globalThis;
    root.__liminalCanvasTrace = {
      events: [],
      draw_count: 0,
      installed_at: Date.now(),
    };

    const record = (method, context, text, x, y) => {
      try {
        const value = String(text ?? "").trim();
        root.__liminalCanvasTrace.draw_count += 1;
        if (!value || value.length > 80 || !/[0-9]/.test(value)) return;
        const canvas = context?.canvas;
        root.__liminalCanvasTrace.events.push({
          at: Date.now(),
          method,
          text: value,
          x: Number(x),
          y: Number(y),
          canvas_width: Number(canvas?.width || 0),
          canvas_height: Number(canvas?.height || 0),
        });
        if (root.__liminalCanvasTrace.events.length > 8000) {
          root.__liminalCanvasTrace.events.splice(0, 2000);
        }
      } catch {
        // Evidence collection must not affect product rendering.
      }
    };

    const wrap = (prototype, method) => {
      if (!prototype || typeof prototype[method] !== "function") return;
      const original = prototype[method];
      Object.defineProperty(prototype, method, {
        configurable: true,
        writable: true,
        value: function liminalCanvasTextWrapper(text, x, y, ...rest) {
          record(method, this, text, x, y);
          return original.call(this, text, x, y, ...rest);
        },
      });
    };

    wrap(root.CanvasRenderingContext2D?.prototype, "fillText");
    wrap(root.CanvasRenderingContext2D?.prototype, "strokeText");
    wrap(root.OffscreenCanvasRenderingContext2D?.prototype, "fillText");
    wrap(root.OffscreenCanvasRenderingContext2D?.prototype, "strokeText");
  });
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
      await sleep(750);
    } else {
      await sleep(400);
    }
  }
  return clicks;
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

async function pageState(page, expectedSymbol) {
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
      "connection lost",
      "no data",
      "ошибка соединения",
      "нет соединения",
      "задержка",
      "данные устарели",
    ].filter((term) => lower.includes(term));
    const candidates = [...document.querySelectorAll("canvas")]
      .filter(visible)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, area: rect.width * rect.height };
      })
      .filter((rect) => rect.width >= 180 && rect.height >= 100)
      .sort((a, b) => b.area - a.area);
    return {
      at: new Date().toISOString(),
      url: location.href,
      title: document.title,
      expected_symbol_visible: text.toUpperCase().includes(symbol.toUpperCase()),
      freshness_terms: terms,
      chart_rect: candidates[0] || null,
      text_sample: text.slice(0, 800),
    };
  }, expectedSymbol);
}

function normalizeClip(rect, viewport) {
  if (!rect) throw new Error("No visible chart canvas found");
  const x = Math.max(0, Math.floor(rect.x));
  const y = Math.max(0, Math.floor(rect.y));
  const width = Math.max(1, Math.min(Math.ceil(rect.width), viewport.width - x));
  const height = Math.max(1, Math.min(Math.ceil(rect.height), viewport.height - y));
  return { x, y, width, height };
}

async function canvasTraceSnapshot(page) {
  return page.evaluate(() => {
    const trace = globalThis.__liminalCanvasTrace || { events: [], draw_count: 0 };
    const events = Array.isArray(trace.events) ? trace.events : [];
    if (!events.length) {
      return { draw_count: trace.draw_count || 0, latest_batch_at: null, numeric_texts: [], events: [] };
    }
    const latestAt = events[events.length - 1].at;
    const batch = events.filter((event) => latestAt - event.at <= 350);
    const numericTexts = [...new Set(batch.map((event) => event.text))].sort();
    return {
      draw_count: trace.draw_count || 0,
      latest_batch_at: new Date(latestAt).toISOString(),
      numeric_texts: numericTexts,
      events: batch.slice(-200),
    };
  });
}

async function captureChartState(page, outputDir, label, clip) {
  const filename = `${label}.png`;
  const target = path.join(outputDir, filename);
  await page.screenshot({ path: target, clip, captureBeyondViewport: false });
  const bytes = await fs.readFile(target);
  return {
    label,
    captured_at: new Date().toISOString(),
    file: filename,
    sha256: sha256(bytes),
    bytes: bytes.length,
    canvas_trace: await canvasTraceSnapshot(page),
  };
}

function imageDifference(leftBytes, rightBytes, channelThreshold = 12) {
  const left = PNG.sync.read(leftBytes);
  const right = PNG.sync.read(rightBytes);
  if (left.width !== right.width || left.height !== right.height) {
    return { comparable: false, changed_pixels: null, changed_ratio: null };
  }
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

async function compareCaptures(outputDir, left, right, threshold) {
  const [leftBytes, rightBytes] = await Promise.all([
    fs.readFile(path.join(outputDir, left.file)),
    fs.readFile(path.join(outputDir, right.file)),
  ]);
  const pixels = imageDifference(leftBytes, rightBytes, threshold.channel_delta);
  const leftText = JSON.stringify(left.canvas_trace.numeric_texts || []);
  const rightText = JSON.stringify(right.canvas_trace.numeric_texts || []);
  return {
    left: left.label,
    right: right.label,
    ...pixels,
    text_signature_changed: leftText !== rightText,
    materially_changed:
      Boolean(pixels.comparable && pixels.changed_ratio >= threshold.changed_ratio) || leftText !== rightText,
  };
}

async function runRound(browser, config, outputRoot, roundNumber) {
  const outputDir = path.join(outputRoot, `round-${roundNumber}`);
  await fs.mkdir(outputDir, { recursive: true });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport(config.viewport);
  await page.setCacheEnabled(false);
  await installCanvasProbe(page);

  const cdp = await page.createCDPSession();
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Fetch.enable", {
    patterns: [{ urlPattern: `*${config.quote_url_fragment}*`, requestStage: "Response" }],
  });

  const quoteResponses = [];
  const newerResponses = [];
  const consoleErrors = [];
  const pageErrors = [];
  const freshnessSamples = [];
  let nonEmptyOrdinal = 0;
  let responseOrdinal = 0;
  let held = null;
  let releasedAt = null;

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleErrors.push({ type: message.type(), text: message.text().slice(0, 1600), at: new Date().toISOString() });
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ message: String(error.message || error), at: new Date().toISOString() });
  });

  cdp.on("Fetch.requestPaused", async (event) => {
    try {
      responseOrdinal += 1;
      const body = await cdp.send("Fetch.getResponseBody", { requestId: event.requestId });
      const bytes = bodyBytes(body);
      if (bytes.length > 0) nonEmptyOrdinal += 1;
      const record = {
        ordinal: responseOrdinal,
        non_empty_ordinal: bytes.length > 0 ? nonEmptyOrdinal : null,
        received_at_ms: Date.now(),
        received_at: new Date().toISOString(),
        response_code: event.responseStatusCode || null,
        body_bytes: bytes.length,
        body_sha256: sha256(bytes),
        body_base64: bytes.toString("base64"),
      };
      quoteResponses.push(record);

      if (bytes.length > 0 && nonEmptyOrdinal === config.held_non_empty_quote_number) {
        held = {
          ...record,
          request_id: event.requestId,
          response_headers: event.responseHeaders || [],
          response_phrase: event.responseStatusText || "OK",
          held_at_ms: Date.now(),
          held_at: new Date().toISOString(),
        };
        return;
      }

      if (held && releasedAt === null && bytes.length > 0) {
        newerResponses.push(record);
      }
      await cdp.send("Fetch.continueResponse", { requestId: event.requestId });
    } catch (error) {
      consoleErrors.push({ type: "probe-error", text: String(error?.stack || error).slice(0, 2000), at: new Date().toISOString() });
      try {
        await cdp.send("Fetch.continueResponse", { requestId: event.requestId });
      } catch {
        // Chromium may already have resolved the paused request.
      }
    }
  });

  const navigation = await page.goto(config.target_url, {
    waitUntil: "domcontentloaded",
    timeout: config.navigation_timeout_ms,
  });
  const cookieTask = dismissCookieBanner(page);
  const initialPageState = await waitFor(
    async () => {
      const state = await pageState(page, config.expected_symbol);
      return state.expected_symbol_visible && state.chart_rect ? state : null;
    },
    config.bootstrap_timeout_ms,
    `round ${roundNumber} chart bootstrap`,
  );
  await cookieTask;
  const clip = normalizeClip(initialPageState.chart_rect, config.viewport);

  await waitFor(
    () => quoteResponses.some((item) => item.non_empty_ordinal === 1),
    config.bootstrap_timeout_ms,
    `round ${roundNumber} first non-empty quote`,
  );
  await sleep(config.render_settle_ms);
  const beforeHold = await captureChartState(page, outputDir, "01-before-hold", clip);

  await waitFor(() => held, config.bootstrap_timeout_ms + config.expected_quote_cadence_ms, `round ${roundNumber} held quote`);
  const holdStart = await captureChartState(page, outputDir, "02-hold-start", clip);

  const holdDeadline = held.held_at_ms + config.hold_ms;
  while (Date.now() < holdDeadline) {
    freshnessSamples.push(await pageState(page, config.expected_symbol));
    await sleep(config.state_sample_interval_ms);
  }

  const distinctNewer = newerResponses.filter((item) => item.body_sha256 !== held.body_sha256);
  let afterNewer = null;
  if (distinctNewer.length > 0) {
    await sleep(config.render_settle_ms);
    afterNewer = await captureChartState(page, outputDir, "03-after-newer", clip);
  }
  const beforeRelease = await captureChartState(page, outputDir, "04-before-release", clip);

  await cdp.send("Fetch.fulfillRequest", {
    requestId: held.request_id,
    responseCode: held.response_code || 200,
    responsePhrase: held.response_phrase,
    responseHeaders: held.response_headers,
    body: held.body_base64,
  });
  releasedAt = Date.now();
  held.released_at_ms = releasedAt;
  held.released_at = new Date(releasedAt).toISOString();
  held.hold_duration_ms = releasedAt - held.held_at_ms;

  const afterRelease = [];
  let elapsed = 0;
  for (const delay of config.post_release_capture_delays_ms) {
    await sleep(Math.max(0, delay - elapsed));
    elapsed = delay;
    afterRelease.push(
      await captureChartState(page, outputDir, `05-after-release-${String(delay).padStart(5, "0")}ms`, clip),
    );
  }

  const finalPageState = await pageState(page, config.expected_symbol);
  const allFreshnessTerms = [...new Set(freshnessSamples.flatMap((sample) => sample.freshness_terms))];
  const comparisons = {};
  if (afterNewer) {
    comparisons.before_to_newer = await compareCaptures(outputDir, beforeHold, afterNewer, config.visual_threshold);
    comparisons.newer_to_release = [];
    comparisons.before_to_release = [];
    for (const capture of afterRelease) {
      comparisons.newer_to_release.push(await compareCaptures(outputDir, afterNewer, capture, config.visual_threshold));
      comparisons.before_to_release.push(await compareCaptures(outputDir, beforeHold, capture, config.visual_threshold));
    }
  }

  const newerVisualChange = Boolean(comparisons.before_to_newer?.materially_changed);
  const anyReleaseMatchesNewer = Boolean(
    comparisons.newer_to_release?.some((item) => !item.materially_changed),
  );
  const anyReleaseMatchesBefore = Boolean(
    comparisons.before_to_release?.some((item) => !item.materially_changed),
  );

  let applicationOutcome = "INCONCLUSIVE_NO_NEWER_RESPONSE";
  if (distinctNewer.length > 0 && !newerVisualChange) {
    applicationOutcome = "APPLICATION_NOT_OBSERVABLE_ON_PUBLIC_CANVAS";
  } else if (newerVisualChange && anyReleaseMatchesBefore && !anyReleaseMatchesNewer) {
    applicationOutcome = "VISIBLE_ROLLBACK_SUPPORTED";
  } else if (newerVisualChange && anyReleaseMatchesNewer) {
    applicationOutcome = "NO_VISIBLE_ROLLBACK_AFTER_OLD_RESPONSE";
  } else if (newerVisualChange) {
    applicationOutcome = "VISIBLE_STATE_CHANGED_BUT_ORDERING_UNCLASSIFIED";
  }

  const result = {
    round: roundNumber,
    started_at: quoteResponses[0]?.received_at || new Date().toISOString(),
    completed_at: new Date().toISOString(),
    navigation_status: navigation?.status() ?? null,
    final_url: page.url(),
    cookie_accept_clicks: await cookieTask,
    clip,
    quote_responses: quoteResponses,
    held_response: held
      ? {
          ordinal: held.ordinal,
          non_empty_ordinal: held.non_empty_ordinal,
          body_bytes: held.body_bytes,
          body_sha256: held.body_sha256,
          body_base64: held.body_base64,
          held_at: held.held_at,
          released_at: held.released_at,
          hold_duration_ms: held.hold_duration_ms,
        }
      : null,
    newer_non_empty_responses: newerResponses,
    distinct_newer_response_count: distinctNewer.length,
    freshness_terms_observed: allFreshnessTerms,
    freshness_sample_count: freshnessSamples.length,
    captures: {
      before_hold: beforeHold,
      hold_start: holdStart,
      after_newer: afterNewer,
      before_release: beforeRelease,
      after_release: afterRelease,
    },
    comparisons,
    application_outcome: applicationOutcome,
    final_page_state: finalPageState,
    console_errors: consoleErrors,
    page_errors: pageErrors,
  };

  await fs.writeFile(path.join(outputDir, "result.json"), `${JSON.stringify(result, null, 2)}\n`);
  await context.close();
  return result;
}

function classify(config, rounds) {
  const counts = Object.fromEntries(
    [...new Set(rounds.map((round) => round.application_outcome))].map((outcome) => [
      outcome,
      rounds.filter((round) => round.application_outcome === outcome).length,
    ]),
  );
  const freshnessGapRounds = rounds.filter(
    (round) =>
      round.held_response?.hold_duration_ms >= config.minimum_freshness_boundary_ms &&
      round.freshness_terms_observed.length === 0,
  ).length;

  let orderingVerdict = "ESCALATE_APPLICATION_ORDER_UNVERIFIED";
  if ((counts.VISIBLE_ROLLBACK_SUPPORTED || 0) >= 2) {
    orderingVerdict = "CONFIRMED_VISIBLE_ROLLBACK";
  } else if ((counts.NO_VISIBLE_ROLLBACK_AFTER_OLD_RESPONSE || 0) >= 2) {
    orderingVerdict = "SUPPORTED_NO_VISIBLE_ROLLBACK";
  } else if ((counts.APPLICATION_NOT_OBSERVABLE_ON_PUBLIC_CANVAS || 0) === rounds.length) {
    orderingVerdict = "PUBLIC_CANVAS_APPLICATION_NOT_OBSERVABLE";
  }

  return {
    verdict: orderingVerdict,
    round_outcomes: counts,
    freshness_state_gap:
      freshnessGapRounds >= 2 ? "REPLICATED" : freshnessGapRounds === 1 ? "OBSERVED_ONCE" : "NOT_ESTABLISHED",
    freshness_gap_rounds: freshnessGapRounds,
    pythia_boundary:
      orderingVerdict === "CONFIRMED_VISIBLE_ROLLBACK"
        ? "The visible chart state changed after newer data and returned to the pre-newer state after the older response was released in at least two rounds."
        : "Transport ordering is exact evidence; application ordering remains bounded by the visible chart and canvas-text evidence collected in each round.",
    cml_boundary:
      "This experiment extends the prior delayed-response memory. It does not convert correlation with ChartStore validation into a shared root cause.",
    ls_boundary:
      freshnessGapRounds >= 2
        ? "The chart remained plausible beyond the expected quote cadence without a visible freshness boundary in repeated rounds."
        : "User-control impact remains bounded to the observed public surface and exact hold windows.",
  };
}

function renderMarkdown(config, rounds, classification, evidenceHash) {
  const rows = rounds
    .map(
      (round) =>
        `| ${round.round} | ${round.held_response?.hold_duration_ms ?? "n/a"} | ${round.distinct_newer_response_count} | ${round.freshness_terms_observed.join(", ") || "none"} | ${round.application_outcome} |`,
    )
    .join("\n");
  return `# LiminalQA · TakeProfit quote application-order experiment\n\n**Target:** \`${config.target_url}\`  \n**Rounds:** ${rounds.length}  \n**Verdict:** **${classification.verdict}**  \n**Freshness state gap:** **${classification.freshness_state_gap}**  \n**Evidence SHA-256:** \`${evidenceHash}\`\n\n## Round matrix\n\n| Round | Hold ms | Distinct newer responses | Freshness terms | Application outcome |\n|---:|---:|---:|---|---|\n${rows}\n\n## What this experiment distinguishes\n\n1. **Visible rollback:** newer quote changes the chart, then releasing the older quote restores the earlier visible state.\n2. **No visible rollback:** newer quote changes the chart, but the old response does not visibly revert it.\n3. **Application not observable:** quote bodies change, but the public chart crop and canvas numeric-text trace do not materially change.\n\n## Lotus reading\n\n### Pythia\n\n${classification.pythia_boundary}\n\n### CML\n\n${classification.cml_boundary}\n\n### LS\n\n${classification.ls_boundary}\n\n## Safety boundary\n\nThe workflow observes one public indicator page and delays only responses naturally initiated by that page. It does not authenticate, call the application API directly, place or modify financial operations, fuzz, load test, exploit, or claim a security vulnerability.\n`;
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
  if (config.rounds !== 3 || config.hold_ms > 120000 || config.hold_ms < 90000) {
    throw new Error("Expected exactly three bounded 90–120 second rounds");
  }

  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-timer-throttling", "--disable-renderer-backgrounding"],
  });

  const rounds = [];
  try {
    for (let round = 1; round <= config.rounds; round += 1) {
      rounds.push(await runRound(browser, config, args["output-dir"], round));
    }
  } finally {
    await browser.close();
  }

  const classification = classify(config, rounds);
  const packet = {
    schema_version: "liminalqa-takeprofit-quote-application-order-result-v1",
    generated_at: new Date().toISOString(),
    target: config.target_url,
    config,
    rounds,
    classification,
    boundaries: config.boundaries,
  };
  const evidenceHash = sha256(Buffer.from(JSON.stringify(packet)));
  packet.evidence_sha256 = evidenceHash;
  await fs.writeFile(
    path.join(args["output-dir"], "quote-application-order-result.json"),
    `${JSON.stringify(packet, null, 2)}\n`,
  );
  await fs.writeFile(
    path.join(args["output-dir"], "quote-application-order-summary.md"),
    renderMarkdown(config, rounds, classification, evidenceHash),
  );
  console.log(JSON.stringify({ classification, evidence_sha256: evidenceHash }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
