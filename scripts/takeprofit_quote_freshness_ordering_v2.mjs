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

function readVarint(buffer, offset) {
  let value = 0n;
  let shift = 0n;
  let cursor = offset;
  while (cursor < buffer.length && shift <= 63n) {
    const byte = BigInt(buffer[cursor]);
    value |= (byte & 0x7fn) << shift;
    cursor += 1;
    if ((byte & 0x80n) === 0n) return { value, next: cursor };
    shift += 7n;
  }
  return null;
}

function printableUtf8(buffer) {
  if (!buffer.length) return null;
  const text = buffer.toString("utf8");
  const chars = [...text];
  const replacementCount = chars.filter((char) => char === "�").length;
  const printableCount = chars.filter((char) => /[\p{L}\p{N}\p{P}\p{Zs}]/u.test(char)).length;
  if (replacementCount > 0 || printableCount / Math.max(chars.length, 1) < 0.8) return null;
  return text.slice(0, 500);
}

function parseProtobuf(buffer, depth = 0, pathPrefix = "", output = []) {
  if (depth > 5 || output.length > 400) return output;
  let offset = 0;
  while (offset < buffer.length && output.length <= 400) {
    const tag = readVarint(buffer, offset);
    if (!tag || tag.value === 0n) break;
    offset = tag.next;
    const field = Number(tag.value >> 3n);
    const wire = Number(tag.value & 7n);
    if (!field || ![0, 1, 2, 5].includes(wire)) break;
    const fieldPath = pathPrefix ? `${pathPrefix}.${field}` : String(field);

    if (wire === 0) {
      const item = readVarint(buffer, offset);
      if (!item) break;
      offset = item.next;
      if (item.value <= BigInt(Number.MAX_SAFE_INTEGER)) {
        output.push({ path: fieldPath, wire, kind: "varint", value: Number(item.value) });
      } else {
        output.push({ path: fieldPath, wire, kind: "varint", value: item.value.toString() });
      }
      continue;
    }

    if (wire === 1) {
      if (offset + 8 > buffer.length) break;
      const doubleValue = buffer.readDoubleLE(offset);
      const uintValue = buffer.readBigUInt64LE(offset);
      if (Number.isFinite(doubleValue)) {
        output.push({ path: fieldPath, wire, kind: "double", value: doubleValue });
      }
      if (uintValue <= BigInt(Number.MAX_SAFE_INTEGER)) {
        output.push({ path: fieldPath, wire, kind: "fixed64", value: Number(uintValue) });
      }
      offset += 8;
      continue;
    }

    if (wire === 5) {
      if (offset + 4 > buffer.length) break;
      const floatValue = buffer.readFloatLE(offset);
      const uintValue = buffer.readUInt32LE(offset);
      if (Number.isFinite(floatValue)) {
        output.push({ path: fieldPath, wire, kind: "float", value: floatValue });
      }
      output.push({ path: fieldPath, wire, kind: "fixed32", value: uintValue });
      offset += 4;
      continue;
    }

    const length = readVarint(buffer, offset);
    if (!length || length.value > BigInt(buffer.length)) break;
    offset = length.next;
    const size = Number(length.value);
    if (offset + size > buffer.length) break;
    const value = buffer.subarray(offset, offset + size);
    offset += size;
    const text = printableUtf8(value);
    if (text) output.push({ path: fieldPath, wire, kind: "string", value: text });
    if (value.length) parseProtobuf(value, depth + 1, fieldPath, output);
  }
  return output;
}

function decodeBody(buffer) {
  const candidates = [{ label: "raw", bytes: buffer }];
  if (buffer.length >= 5 && buffer[0] === 0) {
    const framedLength = buffer.readUInt32BE(1);
    if (framedLength === buffer.length - 5) {
      candidates.push({ label: "grpc_frame", bytes: buffer.subarray(5) });
    }
  }

  let best = { label: "raw", fields: [] };
  for (const candidate of candidates) {
    const fields = parseProtobuf(candidate.bytes);
    if (fields.length > best.fields.length) best = { label: candidate.label, fields };
  }

  const numericValues = best.fields
    .filter((item) => ["varint", "double", "float", "fixed32", "fixed64"].includes(item.kind))
    .map((item) => ({ path: item.path, kind: item.kind, value: item.value }))
    .filter((item) => typeof item.value === "number" && Number.isFinite(item.value));
  const priceCandidates = numericValues
    .filter((item) => item.value >= 100 && item.value <= 100_000_000)
    .filter((item) => !Number.isInteger(item.value) || item.value < 10_000_000)
    .slice(0, 80);
  const timestampCandidates = numericValues
    .filter((item) => item.value >= 1_500_000_000 && item.value <= 4_000_000_000_000)
    .slice(0, 40);
  const strings = best.fields
    .filter((item) => item.kind === "string")
    .map((item) => ({ path: item.path, value: item.value }))
    .slice(0, 60);

  return {
    framing: best.label,
    field_count: best.fields.length,
    price_candidates: priceCandidates,
    timestamp_candidates: timestampCandidates,
    strings,
  };
}

function closestCandidate(decoded, visiblePrice) {
  if (!Number.isFinite(visiblePrice)) return null;
  const candidates = decoded?.price_candidates || [];
  if (!candidates.length) return null;
  const ranked = candidates
    .map((item) => ({ ...item, distance: Math.abs(item.value - visiblePrice) }))
    .sort((a, b) => a.distance - b.distance);
  return ranked[0];
}

async function dismissCookieBanner(page, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  let clicks = 0;
  while (Date.now() < deadline) {
    const clicked = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll("button")];
      const accept = buttons.find((button) => {
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
    const freshnessVocabulary = [
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
    const freshnessTerms = freshnessVocabulary.filter((term) => lower.includes(term));
    const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const contexts = [];
    const symbolRegex = new RegExp(escapeRegExp(symbol), "gi");
    let match;
    while ((match = symbolRegex.exec(text)) && contexts.length < 8) {
      contexts.push(text.slice(match.index, Math.min(text.length, match.index + 160)));
    }
    const numeric = contexts
      .flatMap((context) => [...context.matchAll(/\b\d{2,8}(?:[.,]\d+)?\b/g)].map((item) => Number(item[0].replace(",", "."))))
      .filter((value) => Number.isFinite(value) && value >= 100 && value <= 100_000_000);
    const primaryPrice = numeric.length ? numeric[0] : null;
    const surfaces = [...document.querySelectorAll("canvas, svg")].filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rect.width >= 180 &&
        rect.height >= 100 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0
      );
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
      visible_price_candidates: [...new Set(numeric)].slice(0, 20),
      primary_visible_price: primaryPrice,
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

function priceMatches(value, candidate, tolerance = 0.11) {
  return Number.isFinite(value) && Number.isFinite(candidate) && Math.abs(value - candidate) <= tolerance;
}

function classifyRound(round, config) {
  const held = round.held_response;
  const newerNonEmpty = round.newer_responses.filter((item) => item.body_bytes > 0);
  const beforePrice = round.before_release_state.primary_visible_price;
  const heldClosest = closestCandidate(held?.decoded, beforePrice);
  const newest = newerNonEmpty.at(-1) || null;
  const newestClosest = closestCandidate(newest?.decoded, beforePrice);
  const postPrices = round.post_release_samples
    .map((sample) => sample.primary_visible_price)
    .filter(Number.isFinite);
  const heldCandidate = heldClosest?.value ?? null;
  const newerCandidate = newestClosest?.value ?? null;
  const distinctCandidates =
    Number.isFinite(heldCandidate) && Number.isFinite(newerCandidate)
      ? Math.abs(heldCandidate - newerCandidate) > config.price_match_tolerance
      : false;
  const rollbackObserved =
    distinctCandidates &&
    postPrices.some((price) => priceMatches(price, heldCandidate, config.price_match_tolerance)) &&
    priceMatches(beforePrice, newerCandidate, config.price_match_tolerance);
  const newerStatePreserved =
    distinctCandidates &&
    postPrices.length > 0 &&
    postPrices.every((price) => priceMatches(price, newerCandidate, config.price_match_tolerance));

  let applicationOrdering = "UNVERIFIED";
  if (rollbackObserved) applicationOrdering = "VISIBLE_ROLLBACK_CONFIRMED";
  else if (newerStatePreserved) applicationOrdering = "VISIBLE_NEWER_STATE_PRESERVED";

  const freshnessMarkerVisible = round.hold_samples.some((sample) => sample.freshness_terms.length > 0);
  const chartVisibleAtBoundary =
    round.before_release_state.expected_symbol_visible &&
    round.before_release_state.chart_surface_count > 0;

  return {
    freshness_boundary:
      held && held.hold_duration_ms >= round.requested_hold_ms && chartVisibleAtBoundary
        ? freshnessMarkerVisible
          ? "VISIBLE"
          : "MISSING"
        : "INCONCLUSIVE",
    out_of_order_transport:
      held && newerNonEmpty.length >= config.minimum_newer_non_empty_responses
        ? "CREATED"
        : "INCONCLUSIVE",
    application_ordering: applicationOrdering,
    evidence: {
      newer_non_empty_response_count: newerNonEmpty.length,
      before_release_visible_price: beforePrice,
      held_closest_price_candidate: heldClosest,
      newest_closest_price_candidate: newestClosest,
      distinct_held_and_newer_candidates: distinctCandidates,
      post_release_visible_prices: [...new Set(postPrices)],
      freshness_terms: [...new Set(round.hold_samples.flatMap((sample) => sample.freshness_terms))],
    },
  };
}

async function runRound(browser, config, outputRoot, roundIndex, holdMs) {
  const directory = path.join(outputRoot, `round-${roundIndex + 1}-${holdMs}ms`);
  await fs.mkdir(directory, { recursive: true });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport(config.viewport);
  await page.setCacheEnabled(false);

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
  const failedRequests = [];
  let held = null;
  let nonEmptyOrdinal = 0;
  let releasedAtMs = null;

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleErrors.push({ type: message.type(), text: message.text().slice(0, 2000), at: new Date().toISOString() });
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ message: String(error.message || error), at: new Date().toISOString() });
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

  cdp.on("Fetch.requestPaused", async (event) => {
    try {
      const body = await cdp.send("Fetch.getResponseBody", { requestId: event.requestId });
      const bytes = bodyBytes(body);
      if (bytes.length > 0) nonEmptyOrdinal += 1;
      const record = {
        sequence: quoteResponses.length + 1,
        non_empty_ordinal: bytes.length ? nonEmptyOrdinal : null,
        received_at_ms: Date.now(),
        received_at: new Date().toISOString(),
        url: event.request.url,
        response_code: event.responseStatusCode || null,
        body_bytes: bytes.length,
        body_sha256: sha256(bytes),
        body_base64: bytes.toString("base64"),
        decoded: decodeBody(bytes),
      };
      quoteResponses.push(record);

      if (!held && bytes.length > 0 && nonEmptyOrdinal === config.held_non_empty_response_number) {
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

      if (held && releasedAtMs === null) newerResponses.push(record);
      await cdp.send("Fetch.continueResponse", { requestId: event.requestId });
    } catch (error) {
      consoleErrors.push({ type: "probe-error", text: String(error?.stack || error).slice(0, 3000), at: new Date().toISOString() });
      try {
        await cdp.send("Fetch.continueResponse", { requestId: event.requestId });
      } catch {
        // Chromium may already have resolved this request.
      }
    }
  });

  const navigation = await page.goto(config.target_url, {
    waitUntil: "domcontentloaded",
    timeout: config.navigation_timeout_ms,
  });
  const cookieTask = dismissCookieBanner(page);
  await waitFor(() => held, config.bootstrap_timeout_ms, "first non-empty quote response to hold");
  await waitFor(
    async () => {
      const state = await visibleState(page, config.expected_symbol);
      return state.expected_symbol_visible && state.chart_surface_count > 0 ? state : null;
    },
    config.bootstrap_timeout_ms,
    "public chart and symbol visibility",
  );
  await cookieTask;

  const initialState = await visibleState(page, config.expected_symbol);
  const initialScreenshot = await screenshot(page, directory, "01-initial.png");
  const holdSamples = [];
  while (Date.now() - held.held_at_ms < holdMs) {
    holdSamples.push(await visibleState(page, config.expected_symbol));
    await sleep(config.hold_sample_interval_ms);
  }

  const beforeReleaseState = await visibleState(page, config.expected_symbol);
  const beforeReleaseScreenshot = await screenshot(page, directory, "02-before-release.png");
  await cdp.send("Fetch.fulfillRequest", {
    requestId: held.request_id,
    responseCode: held.response_code || 200,
    responsePhrase: held.response_phrase,
    responseHeaders: held.response_headers,
    body: held.body_base64,
  });
  releasedAtMs = Date.now();
  held.released_at_ms = releasedAtMs;
  held.released_at = new Date(releasedAtMs).toISOString();
  held.hold_duration_ms = releasedAtMs - held.held_at_ms;

  const postReleaseSamples = [];
  const highFrequencyDeadline = Date.now() + config.post_release_high_frequency_ms;
  while (Date.now() < highFrequencyDeadline) {
    postReleaseSamples.push(await visibleState(page, config.expected_symbol));
    await sleep(config.high_frequency_sample_interval_ms);
  }
  const postDeadline = Date.now() + config.post_release_observation_ms;
  while (Date.now() < postDeadline) {
    postReleaseSamples.push(await visibleState(page, config.expected_symbol));
    await sleep(config.post_release_sample_interval_ms);
  }

  const finalState = await visibleState(page, config.expected_symbol);
  const finalScreenshot = await screenshot(page, directory, "03-after-release.png");
  const round = {
    round: roundIndex + 1,
    requested_hold_ms: holdMs,
    navigation_status: navigation?.status() ?? null,
    final_url: page.url(),
    cookie_accept_clicks: await cookieTask,
    initial_state: initialState,
    before_release_state: beforeReleaseState,
    final_state: finalState,
    hold_samples: holdSamples,
    post_release_samples: postReleaseSamples,
    quote_responses: quoteResponses.map(({ request_id, response_headers, response_phrase, ...item }) => item),
    newer_responses: newerResponses,
    held_response: held
      ? Object.fromEntries(
          Object.entries(held).filter(([key]) => !["request_id", "response_headers", "response_phrase"].includes(key)),
        )
      : null,
    screenshots: {
      initial: initialScreenshot,
      before_release: beforeReleaseScreenshot,
      after_release: finalScreenshot,
    },
    console_errors: consoleErrors,
    page_errors: pageErrors,
    failed_requests: failedRequests,
  };
  round.classification = classifyRound(round, config);
  await fs.writeFile(path.join(directory, "round-result.json"), `${JSON.stringify(round, null, 2)}\n`);
  await context.close();
  return round;
}

function classifyPacket(rounds) {
  const validFreshness = rounds.filter((round) => round.classification.freshness_boundary !== "INCONCLUSIVE");
  const missingFreshness = validFreshness.filter((round) => round.classification.freshness_boundary === "MISSING");
  const transportCreated = rounds.filter((round) => round.classification.out_of_order_transport === "CREATED");
  const rollback = rounds.filter((round) => round.classification.application_ordering === "VISIBLE_ROLLBACK_CONFIRMED");
  const preserved = rounds.filter((round) => round.classification.application_ordering === "VISIBLE_NEWER_STATE_PRESERVED");

  let verdict = "INCONCLUSIVE";
  if (rollback.length > 0 && missingFreshness.length >= 2) {
    verdict = "CONFIRMED_VISIBLE_ROLLBACK_AND_FRESHNESS_GAP";
  } else if (validFreshness.length === rounds.length && missingFreshness.length === rounds.length) {
    verdict = "CONFIRMED_FRESHNESS_BOUNDARY_GAP";
  } else if (missingFreshness.length >= 2) {
    verdict = "SUPPORTED_FRESHNESS_BOUNDARY_GAP";
  }

  return {
    verdict,
    checks: {
      three_independent_rounds: rounds.length === 3 ? "PASS" : "FAIL",
      cadence_exceeding_holds: rounds.every((round) => round.held_response?.hold_duration_ms >= round.requested_hold_ms) ? "PASS" : "FAIL",
      visible_freshness_boundary: missingFreshness.length === 0 ? "PASS" : "FAIL",
      older_after_newer_transport: transportCreated.length === rounds.length ? "CONFIRMED_ALL_ROUNDS" : `${transportCreated.length}_OF_${rounds.length}`,
      visible_application_rollback: rollback.length ? "CONFIRMED" : "NOT_CONFIRMED",
      visible_newer_state_preserved: preserved.length ? `${preserved.length}_OF_${rounds.length}` : "NOT_CONFIRMED",
    },
    counts: {
      rounds: rounds.length,
      freshness_missing: missingFreshness.length,
      transport_created: transportCreated.length,
      visible_rollbacks: rollback.length,
      visible_newer_state_preserved: preserved.length,
      application_ordering_unverified: rounds.length - rollback.length - preserved.length,
    },
    pythia_boundary:
      "The freshness verdict is based on three cadence-exceeding public-page observations. A visible rollback is reported only when the DOM price can be bound to distinct held and newer response candidates.",
    cml_boundary:
      "Repeated missing freshness markers may become recurring bounded evidence; response ordering remains a separate causal edge and is not silently promoted to a user-visible rollback.",
    ls_boundary:
      "A plausible live chart retained beyond its expected update cadence without a freshness marker reduces the user's ability to distinguish current state from retained state.",
  };
}

function renderMarkdown(packet) {
  const rows = packet.rounds
    .map((round) => {
      const c = round.classification;
      return `| ${round.round} | ${round.requested_hold_ms} | ${round.held_response?.hold_duration_ms ?? "n/a"} | ${c.evidence.newer_non_empty_response_count} | ${c.freshness_boundary} | ${c.out_of_order_transport} | ${c.application_ordering} |`;
    })
    .join("\n");
  return `# TakeProfit quote freshness and ordering v2\n\n**Target:** \`${packet.target}\`  \n**Verdict:** **${packet.classification.verdict}**  \n**Evidence SHA-256:** \`${packet.evidence_sha256}\`\n\n## Three-round matrix\n\n| Round | Requested hold ms | Actual hold ms | Newer non-empty responses | Freshness boundary | Older-after-newer transport | Application ordering |\n|---:|---:|---:|---:|---|---|---|\n${rows}\n\n## Aggregate checks\n\n- Three independent rounds: **${packet.classification.checks.three_independent_rounds}**\n- Cadence-exceeding holds: **${packet.classification.checks.cadence_exceeding_holds}**\n- Visible freshness boundary: **${packet.classification.checks.visible_freshness_boundary}**\n- Older-after-newer transport: **${packet.classification.checks.older_after_newer_transport}**\n- Visible application rollback: **${packet.classification.checks.visible_application_rollback}**\n- Visible newer-state preservation: **${packet.classification.checks.visible_newer_state_preserved}**\n\n## Lotus reading\n\n### Pythia\n\n${packet.classification.pythia_boundary}\n\n### CML\n\n${packet.classification.cml_boundary}\n\n### LS\n\n${packet.classification.ls_boundary}\n\n## Boundary\n\nThe workflow observes one allowlisted public page and delays only naturally initiated quote responses inside the browser. It does not authenticate, call the quote endpoint directly, modify TakeProfit server state, place financial operations, fuzz, load test, exploit, or claim a security vulnerability.\n`;
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
  if (JSON.stringify(config.hold_durations_ms) !== JSON.stringify([90000, 105000, 120000])) {
    throw new Error("The exact three cadence-aware hold durations are required");
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

  const rounds = [];
  try {
    for (let index = 0; index < config.hold_durations_ms.length; index += 1) {
      rounds.push(await runRound(browser, config, args["output-dir"], index, config.hold_durations_ms[index]));
    }
  } finally {
    await browser.close();
  }

  const classification = classifyPacket(rounds);
  const packet = {
    schema_version: "liminalqa-takeprofit-quote-freshness-ordering-result-v2",
    generated_at: new Date().toISOString(),
    target: config.target_url,
    config,
    rounds,
    classification,
    boundaries: config.boundaries,
    authority: {
      mode: "evidence_only",
      grants: {
        ownership: false,
        approval: false,
        execution: false,
        delivery: false,
        deployment: false,
        merge: false,
      },
    },
  };
  const canonical = Buffer.from(`${JSON.stringify(packet, null, 2)}\n`);
  packet.evidence_sha256 = sha256(canonical);
  await fs.writeFile(path.join(args["output-dir"], "quote-freshness-ordering-result.json"), `${JSON.stringify(packet, null, 2)}\n`);
  await fs.writeFile(path.join(args["output-dir"], "quote-freshness-ordering-summary.md"), renderMarkdown(packet));
  console.log(JSON.stringify({ verdict: classification.verdict, checks: classification.checks, evidence_sha256: packet.evidence_sha256 }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
