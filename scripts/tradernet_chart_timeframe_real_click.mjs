#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key}`);
    result[key.slice(2)] = value;
  }
  return result;
}

function parseRequest(url) {
  try {
    const parsed = new URL(url);
    const payload = JSON.parse(parsed.searchParams.get("q"));
    return {
      id: payload.params?.id ?? null,
      timeframe: payload.params?.timeframe ?? null,
      interval: payload.params?.interval ?? null,
      interval_mode: payload.params?.intervalMode ?? null,
      date_from: payload.params?.date_from ?? null,
      date_to: payload.params?.date_to ?? null,
      count: payload.params?.count ?? null,
      demo: payload.params?.demo ?? null,
    };
  } catch {
    return null;
  }
}

function inspectHloc(json, ticker) {
  const candles = json?.hloc?.[ticker];
  const times = json?.xSeries?.[ticker];
  const volumes = json?.vl?.[ticker];
  const violations = [];
  if (!Array.isArray(candles)) violations.push("HLOC_MISSING");
  if (!Array.isArray(times)) violations.push("TIMESTAMPS_MISSING");
  if (!Array.isArray(volumes)) violations.push("VOLUMES_MISSING");
  if (!Array.isArray(candles) || !Array.isArray(times) || !Array.isArray(volumes)) {
    return { candle_count: 0, timestamp_count: 0, volume_count: 0, violations };
  }
  if (candles.length !== times.length) violations.push("HLOC_TIMESTAMP_LENGTH_MISMATCH");
  if (candles.length !== volumes.length) violations.push("HLOC_VOLUME_LENGTH_MISMATCH");

  let previous = null;
  const seen = new Set();
  candles.forEach((row, index) => {
    if (!Array.isArray(row) || row.length < 4) {
      violations.push(`CANDLE_SHAPE_INVALID:${index}`);
      return;
    }
    const [high, low, open, close] = row.map(Number);
    if (![high, low, open, close].every(Number.isFinite)) violations.push(`CANDLE_NON_NUMERIC:${index}`);
    if (high < low) violations.push(`HIGH_BELOW_LOW:${index}`);
    if (open < low || open > high) violations.push(`OPEN_OUTSIDE_RANGE:${index}`);
    if (close < low || close > high) violations.push(`CLOSE_OUTSIDE_RANGE:${index}`);

    const timestamp = Number(times[index]);
    if (!Number.isFinite(timestamp)) violations.push(`TIMESTAMP_NON_NUMERIC:${index}`);
    else {
      if (seen.has(timestamp)) violations.push(`TIMESTAMP_DUPLICATE:${index}`);
      if (Number.isFinite(previous) && timestamp <= previous) violations.push(`TIMESTAMP_NOT_INCREASING:${index}`);
      seen.add(timestamp);
      previous = timestamp;
    }

    const volume = Number(volumes[index]);
    if (!Number.isFinite(volume)) violations.push(`VOLUME_NON_NUMERIC:${index}`);
    else if (volume < 0) violations.push(`VOLUME_NEGATIVE:${index}`);
  });

  return {
    candle_count: candles.length,
    timestamp_count: times.length,
    volume_count: volumes.length,
    first_timestamp: times.length ? Number(times[0]) : null,
    last_timestamp: times.length ? Number(times.at(-1)) : null,
    violations: violations.slice(0, 100),
  };
}

async function state(page) {
  return page.evaluate(() => {
    const opener = document.querySelector(".js-intervalSelector");
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width >= 120 && rect.height >= 80 && style.display !== "none" && style.visibility !== "hidden";
    };
    return {
      selected_value: opener?.getAttribute("data-value") ?? null,
      selected_text: opener?.textContent?.replace(/\s+/g, " ").trim() ?? null,
      chart_visible: [...document.querySelectorAll('canvas, svg, [id*="chart" i], [class*="chart" i]')].some(visible),
      final_url: location.href,
      title: document.title,
    };
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  const profile = config.profiles.find((item) => item.id === "desktop_broadband");
  if (!profile || config.target_url !== "https://tradernet.ru/charts/MICEXINDEXCF") {
    throw new Error("Unexpected configuration");
  }

  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.setCacheEnabled(false);

  const observations = [];
  const bodyTasks = [];
  page.on("response", (response) => {
    if (!response.url().includes("getHloc")) return;
    const observation = {
      status: response.status(),
      url: response.url(),
      shape: parseRequest(response.url()),
      observed_at: new Date().toISOString(),
      body_analysis: null,
      body_error: null,
    };
    observations.push(observation);
    bodyTasks.push(
      (async () => {
        try {
          observation.body_analysis = inspectHloc(await response.json(), config.ticker);
        } catch (error) {
          observation.body_error = String(error?.message || error);
        }
      })()
    );
  });

  let navigationError = null;
  try {
    await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  } catch (error) {
    navigationError = String(error?.stack || error);
  }

  const initialDeadline = Date.now() + 35_000;
  while (!observations.some((item) => item.shape?.interval === "D1") && Date.now() < initialDeadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  await Promise.allSettled(bodyTasks);
  const before = await state(page);
  await page.screenshot({ path: path.join(args["output-dir"], "before-D1.png"), fullPage: true });

  const openerSelector = ".js-intervalSelector[data-value=\"D1\"]";
  const optionSelector = ".js-selectInterval .js-chart-click[data-value=\"H1\"]";
  let action = { opened: false, option_visible: false, selected: false, error: null };
  try {
    await page.waitForSelector(openerSelector, { visible: true, timeout: 10_000 });
    await page.click(openerSelector);
    action.opened = true;
    await page.waitForSelector(optionSelector, { visible: true, timeout: 10_000 });
    action.option_visible = true;
    const optionText = await page.$eval(optionSelector, (element) => element.textContent?.replace(/\s+/g, " ").trim() ?? null);
    await page.click(optionSelector);
    action = { ...action, selected: true, target_value: "H1", target_text: optionText };
  } catch (error) {
    action.error = String(error?.stack || error);
  }

  const h1Deadline = Date.now() + 35_000;
  while (!observations.some((item) => item.shape?.interval === "H1") && Date.now() < h1Deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  await new Promise((resolve) => setTimeout(resolve, 3000));
  await Promise.allSettled(bodyTasks);
  const after = await state(page);
  await page.screenshot({ path: path.join(args["output-dir"], "after-H1.png"), fullPage: true });

  const d1 = observations.find((item) => item.shape?.interval === "D1") ?? null;
  const h1 = observations.find((item) => item.shape?.interval === "H1") ?? null;
  const h1Clean = Boolean(h1?.body_analysis?.candle_count > 0 && h1.body_analysis.violations.length === 0);

  let verdict;
  if (navigationError) verdict = "EVIDENCE_FAILURE";
  else if (!before.chart_visible || before.selected_value !== "D1") verdict = "INVALID_INITIAL_STATE";
  else if (!action.opened || !action.option_visible || !action.selected) verdict = "TRUSTED_CLICK_FAILED";
  else if (!h1) verdict = "TRUSTED_CLICK_NO_H1_REQUEST";
  else if (after.selected_value !== "H1" || !after.chart_visible) verdict = "UI_REQUEST_STATE_DIVERGENCE";
  else if (h1.shape?.timeframe === d1?.shape?.timeframe) verdict = "TIMEFRAME_DID_NOT_CHANGE";
  else if (!h1Clean) verdict = "H1_DATA_INTEGRITY_WARN";
  else verdict = "TRANSITION_PASS";

  const result = {
    schema_version: "liminalqa-chart-timeframe-trusted-click-v1",
    verdict,
    target_url: config.target_url,
    ticker: config.ticker,
    navigation_error: navigationError,
    before,
    action,
    after,
    d1_observation: d1,
    h1_observation: h1,
    observations,
    generated_at: new Date().toISOString(),
  };
  await fs.writeFile(path.join(args["output-dir"], "timeframe-transition-result.json"), `${JSON.stringify(result, null, 2)}\n`);
  await fs.writeFile(
    path.join(args["output-dir"], "timeframe-transition-summary.md"),
    [
      "# Tradernet D1 → H1 trusted-click transition",
      "",
      `**Verdict:** ${verdict}  `,
      `**UI:** ${before.selected_value ?? "n/a"} → ${after.selected_value ?? "n/a"}  `,
      `**Requests:** ${observations.length}`,
      "",
      "| Phase | Timeframe | Interval | Candles | Violations | Status |",
      "|---|---:|---|---:|---:|---:|",
      `| Initial | ${d1?.shape?.timeframe ?? "n/a"} | ${d1?.shape?.interval ?? "n/a"} | ${d1?.body_analysis?.candle_count ?? 0} | ${d1?.body_analysis?.violations.length ?? "n/a"} | ${d1?.status ?? "n/a"} |`,
      `| After switch | ${h1?.shape?.timeframe ?? "n/a"} | ${h1?.shape?.interval ?? "n/a"} | ${h1?.body_analysis?.candle_count ?? 0} | ${h1?.body_analysis?.violations.length ?? "n/a"} | ${h1?.status ?? "n/a"} |`,
      "",
      "> Exactly one visible UI option was selected with Puppeteer's trusted mouse event. No direct API request was issued.",
      "",
    ].join("\n"),
    "utf8"
  );

  await context.close();
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
  if (verdict === "EVIDENCE_FAILURE") process.exitCode = 1;
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
