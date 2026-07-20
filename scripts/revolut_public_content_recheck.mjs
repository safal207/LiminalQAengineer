#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

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

async function dismissConsent(page) {
  const labels = ["accept all", "accept", "allow all", "agree", "i agree", "принять", "zgadzam się", "zaakceptuj"];
  let clicks = 0;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const clicked = await page.evaluate((allowed) => {
      const candidates = [...document.querySelectorAll("button, [role='button']")];
      const target = candidates.find((element) => {
        const text = (element.textContent || element.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim().toLowerCase();
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return allowed.includes(text) && rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
      });
      if (!target) return false;
      target.click();
      return true;
    }, labels).catch(() => false);
    if (!clicked) break;
    clicks += 1;
    await sleep(700);
  }
  return clicks;
}

async function inspectPage(page, target, config) {
  return page.evaluate((targetId, maxChars) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const body = normalize(document.body?.innerText || "");
    const lower = body.toLowerCase();
    const context = (needle, before = 180, after = 650) => {
      const index = lower.indexOf(needle.toLowerCase());
      if (index < 0) return null;
      return body.slice(Math.max(0, index - before), Math.min(body.length, index + after));
    };
    const contexts = (needle, limit = 10) => {
      const output = [];
      let from = 0;
      const loweredNeedle = needle.toLowerCase();
      while (output.length < limit) {
        const index = lower.indexOf(loweredNeedle, from);
        if (index < 0) break;
        output.push(body.slice(Math.max(0, index - 120), Math.min(body.length, index + 520)));
        from = index + loweredNeedle.length;
      }
      return output;
    };
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
    };
    const codeBlocks = [...document.querySelectorAll("pre, code")]
      .filter(visible)
      .map((element) => normalize(element.textContent))
      .filter(Boolean);

    const result = {
      target_id: targetId,
      title: document.title,
      html_lang: document.documentElement.lang,
      body_length: body.length,
      body_text_sha256_input: body,
      body_sample: body.slice(0, maxChars),
      headings: [...document.querySelectorAll("h1,h2,h3")].filter(visible).map((element) => normalize(element.textContent)).slice(0, 100),
      code_block_count: codeBlocks.length,
      contexts: {},
      detections: {},
    };

    if (targetId === "btc-pln") {
      const hero = context("our current rate");
      const priceSection = context("price of btc in pln");
      const heading = context("btc/pln");
      const marketStats = context("market cap");
      result.contexts = {heading, hero, price_section: priceSection, market_stats: marketStats};
      result.detections = {
        heading_btc_pln: Boolean(heading),
        market_context_pln: Boolean(marketStats && /zł|PLN/i.test(marketStats)),
        hero_uses_eur: Boolean(hero && /EUR|€/i.test(hero)),
        price_of_btc_in_pln_section_uses_eur: Boolean(priceSection && /EUR|€/i.test(priceSection)),
      };
    } else if (targetId === "sol-usd") {
      const wallet = context("send them directly to another one of your crypto wallets");
      const withdraw = context("withdraw your solana tokens");
      result.contexts = {wallet, withdraw};
      result.detections = {
        offers_solana_external_wallet_transfer: Boolean((wallet || withdraw) && /Solana/i.test(wallet || withdraw || "")),
        restricts_parenthetical_to_bitcoin_ethereum: Boolean((wallet || withdraw) && /Bitcoin and Ethereum only/i.test(wallet || withdraw || "")),
      };
    } else if (targetId === "x-api-docs") {
      const everyRequest = context("Every request to the API must include");
      const nodeExample = context("/api/1.0/crypto-exchange/orders");
      const lastTrades = context("/api/1.0/public/last-trades");
      const publicOrderBook = context("/api/1.0/public/order-book/BTC-USD");
      const balances = context("/api/1.0/balances");
      const configuration = context("/api/1.0/configuration/currencies");
      const ethContexts = contexts('"aid": "ETH"', 8);
      const oldNodeBlocks = codeBlocks.filter((block) => block.includes("/api/1.0/crypto-exchange/orders"));
      const publicBearerBlocks = codeBlocks.filter((block) => /\/public\/(last-trades|order-book\/BTC-USD)/.test(block) && /Authorization:\s*Bearer/i.test(block));
      const authenticatedCurlBlocks = codeBlocks.filter((block) => /curl -X (GET|POST|PUT|DELETE)/.test(block) && /X-Revx-Timestamp/i.test(block) && /X-Revx-Signature/i.test(block));
      const authenticatedWithoutKey = authenticatedCurlBlocks.filter((block) => !/X-Revx-API-Key/i.test(block));
      const btcOrderBookIndex = lower.indexOf("/api/1.0/public/order-book/btc-usd");
      const ethAfterBtc = btcOrderBookIndex >= 0 ? lower.slice(btcOrderBookIndex, btcOrderBookIndex + 5500).includes('"aid": "eth"') : false;
      result.contexts = {
        every_request: everyRequest,
        node_example: nodeExample,
        public_last_trades: lastTrades,
        public_order_book: publicOrderBook,
        balances_curl: balances,
        configuration_curl: configuration,
        eth_samples: ethContexts,
      };
      result.detections = {
        every_request_requires_custom_headers: Boolean(everyRequest && /X-Revx-API-Key|authentication headers/i.test(everyRequest)),
        public_examples_use_bearer: publicBearerBlocks.length > 0,
        public_bearer_code_block_count: publicBearerBlocks.length,
        node_example_uses_obsolete_path: oldNodeBlocks.length > 0,
        node_example_uses_old_symbol_payload: oldNodeBlocks.some((block) => /BTC\/USD/.test(block) && /type/.test(block) && /qty/.test(block)),
        authenticated_curl_block_count: authenticatedCurlBlocks.length,
        authenticated_curl_without_api_key_count: authenticatedWithoutKey.length,
        btc_public_order_book_sample_contains_eth: ethAfterBtc,
      };
    }
    return result;
  }, target.id, config.max_body_chars);
}

async function observe(browser, config, profile, target, outputDir) {
  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  const consoleEntries = [];
  const failedRequests = [];
  page.on("console", (message) => {
    if (consoleEntries.length < 200) consoleEntries.push({type: message.type(), text: message.text().slice(0, 1000)});
  });
  page.on("requestfailed", (request) => {
    if (failedRequests.length < 100) failedRequests.push({url: request.url(), error: request.failure()?.errorText || null});
  });

  let response = null;
  let navigationError = null;
  const started = Date.now();
  try {
    response = await page.goto(target.url, {waitUntil: "domcontentloaded", timeout: config.navigation_timeout_ms});
  } catch (error) {
    navigationError = String(error?.message || error);
  }
  const consentClicks = await dismissConsent(page).catch(() => 0);
  await sleep(config.settle_ms);
  const inspected = await inspectPage(page, target, config);
  const body = inspected.body_text_sha256_input;
  delete inspected.body_text_sha256_input;
  inspected.body_text_sha256 = sha256(body);

  const screenshot = `${profile.id}-${target.id}.png`;
  await page.screenshot({path: path.join(outputDir, screenshot), fullPage: true}).catch(() => null);
  const result = {
    profile: profile.id,
    target_id: target.id,
    requested_url: target.url,
    final_url: page.url(),
    status: response?.status() ?? null,
    navigation_error: navigationError,
    wall_time_ms: Date.now() - started,
    consent_clicks: consentClicks,
    page: inspected,
    console: {
      error_count: consoleEntries.filter((entry) => entry.type === "error").length,
      warning_count: consoleEntries.filter((entry) => entry.type === "warning").length,
      entries: consoleEntries,
    },
    failed_requests: failedRequests,
    screenshot,
  };
  await page.close();
  return result;
}

function aggregate(observations, profileCount) {
  const byTarget = (id) => observations.filter((entry) => entry.target_id === id);
  const btc = byTarget("btc-pln");
  const sol = byTarget("sol-usd");
  const docs = byTarget("x-api-docs");
  const allProfiles = (entries, predicate) => entries.length === profileCount && entries.every(predicate);
  return {
    verdicts: {
      currency_context_mismatch: allProfiles(btc, (entry) =>
        entry.page.detections.heading_btc_pln &&
        entry.page.detections.market_context_pln &&
        entry.page.detections.hero_uses_eur &&
        entry.page.detections.price_of_btc_in_pln_section_uses_eur,
      ) ? "CONFIRMED_PUBLIC_SURFACE" : "NOT_CONFIRMED",
      solana_external_wallet_copy_conflict: allProfiles(sol, (entry) =>
        entry.page.detections.offers_solana_external_wallet_transfer &&
        entry.page.detections.restricts_parenthetical_to_bitcoin_ethereum,
      ) ? "CONFIRMED_PUBLIC_SURFACE" : "NOT_CONFIRMED",
      public_auth_documentation_conflict: allProfiles(docs, (entry) =>
        entry.page.detections.every_request_requires_custom_headers && entry.page.detections.public_examples_use_bearer,
      ) ? "CONFIRMED_DOCUMENTATION_CONFLICT" : "NOT_CONFIRMED",
      node_signing_example_obsolete: allProfiles(docs, (entry) =>
        entry.page.detections.node_example_uses_obsolete_path && entry.page.detections.node_example_uses_old_symbol_payload,
      ) ? "CONFIRMED_DOCUMENTATION_DEFECT" : "NOT_CONFIRMED",
      authenticated_curl_missing_api_key: allProfiles(docs, (entry) =>
        entry.page.detections.authenticated_curl_without_api_key_count > 0,
      ) ? "CONFIRMED_DOCUMENTATION_DEFECT" : "NOT_CONFIRMED",
      btc_order_book_eth_sample: allProfiles(docs, (entry) =>
        entry.page.detections.btc_public_order_book_sample_contains_eth,
      ) ? "CONFIRMED_DOCUMENTATION_DEFECT" : "NOT_CONFIRMED",
    },
    target_matrix: observations.map((entry) => ({
      profile: entry.profile,
      target_id: entry.target_id,
      status: entry.status,
      final_url: entry.final_url,
      body_text_sha256: entry.page.body_text_sha256,
      detections: entry.page.detections,
      screenshot: entry.screenshot,
    })),
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = args.config;
  const chromePath = args.chrome;
  const outputDir = args["output-dir"];
  if (!configPath || !chromePath || !outputDir) throw new Error("Required: --config --chrome --output-dir");
  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  await fs.rm(outputDir, {recursive: true, force: true});
  await fs.mkdir(outputDir, {recursive: true});

  const browser = await puppeteer.launch({executablePath: chromePath, headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage"]});
  const observations = [];
  try {
    for (const profile of config.profiles) {
      for (const target of config.targets) observations.push(await observe(browser, config, profile, target, outputDir));
    }
  } finally {
    await browser.close();
  }

  const result = {
    schema_version: "liminalqa-revolut-public-content-recheck-result-v0.2",
    observed_at: new Date().toISOString(),
    center_of_coordinates: {
      O: "official public URL + browser profile + viewport + unauthenticated state + observation time",
      N: "passive unauthenticated browser",
      axes: {
        X: "product/docs route -> section -> claim/example",
        Y: "consistent -> contradictory -> ambiguous",
        Z: "desktop/mobile rendering context",
        T: "navigation -> settled content capture",
      },
    },
    aggregate: aggregate(observations, config.profiles.length),
    observations,
    boundaries: config.boundaries,
    limitations: config.limitations,
    authority: {
      mode: "evidence_only",
      grants: {ownership: false, approval: false, execution: false, external_submission: false, delivery: false, deployment: false, merge: false},
    },
  };
  const resultText = `${JSON.stringify(result, null, 2)}\n`;
  await fs.writeFile(path.join(outputDir, "revolut-public-content-recheck-result.json"), resultText);
  const rows = result.aggregate.target_matrix.map((entry) =>
    `| ${entry.profile} | ${entry.target_id} | ${entry.status ?? "n/a"} | ${Object.entries(entry.detections).filter(([, value]) => value === true || (typeof value === "number" && value > 0)).map(([key, value]) => `${key}=${value}`).join("; ")} |`,
  ).join("\n");
  const summary = `# Revolut public content recheck v0.2\n\nObserved: ${result.observed_at}\n\n## Verdicts\n\n${Object.entries(result.aggregate.verdicts).map(([key, value]) => `- ${key}: **${value}**`).join("\n")}\n\n## Matrix\n\n| Profile | Target | HTTP | Positive detections |\n|---|---|---:|---|\n${rows}\n\n## Boundary\n\nPublic rendered content only; no login, accounts, direct API calls, forms, trading, fuzzing, load testing, or server-state changes.\n`;
  await fs.writeFile(path.join(outputDir, "revolut-public-content-recheck-summary.md"), summary);
  await fs.writeFile(path.join(outputDir, "SHA256SUMS.txt"), `${sha256(resultText)}  revolut-public-content-recheck-result.json\n${sha256(summary)}  revolut-public-content-recheck-summary.md\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
