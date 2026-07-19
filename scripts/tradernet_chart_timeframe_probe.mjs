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

function requestShape(url) {
  try {
    const parsed = new URL(url);
    const rawQuery = parsed.searchParams.get("q");
    if (!rawQuery) return null;
    const q = JSON.parse(rawQuery);
    return {
      id: q.params?.id ?? null,
      timeframe: q.params?.timeframe ?? null,
      interval: q.params?.interval ?? null,
      interval_mode: q.params?.intervalMode ?? null,
      date_from: q.params?.date_from ?? null,
      date_to: q.params?.date_to ?? null,
      count: q.params?.count ?? null,
      demo: q.params?.demo ?? null,
    };
  } catch {
    return null;
  }
}

function analyzeHloc(json, ticker) {
  const candles = json?.hloc?.[ticker];
  const timestamps = json?.xSeries?.[ticker];
  const volumes = json?.vl?.[ticker];
  const violations = [];

  if (!Array.isArray(candles)) violations.push("HLOC_MISSING");
  if (!Array.isArray(timestamps)) violations.push("TIMESTAMPS_MISSING");
  if (!Array.isArray(volumes)) violations.push("VOLUMES_MISSING");
  if (!Array.isArray(candles) || !Array.isArray(timestamps) || !Array.isArray(volumes)) {
    return { candle_count: 0, timestamp_count: 0, volume_count: 0, violations };
  }

  if (candles.length !== timestamps.length) violations.push("HLOC_TIMESTAMP_LENGTH_MISMATCH");
  if (candles.length !== volumes.length) violations.push("HLOC_VOLUME_LENGTH_MISMATCH");

  let previousTimestamp = null;
  const seen = new Set();
  candles.forEach((row, index) => {
    if (!Array.isArray(row) || row.length < 4) {
      violations.push(`CANDLE_SHAPE_INVALID:${index}`);
      return;
    }
    const [high, low, open, close] = row.map(Number);
    if (![high, low, open, close].every(Number.isFinite)) {
      violations.push(`CANDLE_NON_NUMERIC:${index}`);
      return;
    }
    if (high < low) violations.push(`HIGH_BELOW_LOW:${index}`);
    if (open < low || open > high) violations.push(`OPEN_OUTSIDE_RANGE:${index}`);
    if (close < low || close > high) violations.push(`CLOSE_OUTSIDE_RANGE:${index}`);

    const timestamp = Number(timestamps[index]);
    if (!Number.isFinite(timestamp)) {
      violations.push(`TIMESTAMP_NON_NUMERIC:${index}`);
    } else {
      if (seen.has(timestamp)) violations.push(`TIMESTAMP_DUPLICATE:${index}`);
      if (Number.isFinite(previousTimestamp) && timestamp <= previousTimestamp) {
        violations.push(`TIMESTAMP_NOT_INCREASING:${index}`);
      }
      seen.add(timestamp);
      previousTimestamp = timestamp;
    }

    const volume = Number(volumes[index]);
    if (!Number.isFinite(volume)) violations.push(`VOLUME_NON_NUMERIC:${index}`);
    if (volume < 0) violations.push(`VOLUME_NEGATIVE:${index}`);
  });

  return {
    candle_count: candles.length,
    timestamp_count: timestamps.length,
    volume_count: volumes.length,
    first_timestamp: timestamps.length ? Number(timestamps[0]) : null,
    last_timestamp: timestamps.length ? Number(timestamps.at(-1)) : null,
    violations: violations.slice(0, 100),
  };
}

async function chartState(page) {
  return page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rect.width >= 120 &&
        rect.height >= 80 &&
        style.display !== "none" &&
        style.visibility !== "hidden"
      );
    };
    const opener = document.querySelector(".js-intervalSelector");
    const selectedText = opener?.textContent?.replace(/\s+/g, " ").trim() ?? null;
    const selectedValue = opener?.getAttribute("data-value") ?? null;
    const chartSurfaces = [
      ...document.querySelectorAll(
        'canvas, svg, [id*="chart" i], [class*="chart" i], [id*="graph" i], [class*="graph" i]'
      ),
    ].filter(visible);
    return {
      selected_text: selectedText,
      selected_value: selectedValue,
      chart_visible: chartSurfaces.length > 0,
      visible_chart_surface_count: chartSurfaces.length,
      title: document.title,
      final_url: location.href,
    };
  });
}

async function clickExactInterval(page, value) {
  return page.evaluate((targetValue) => {
    const opener = document.querySelector(".js-intervalSelector");
    if (!opener) return { opened: false, selected: false, reason: "opener_not_found" };
    opener.click();
    const option = document.querySelector(`.js-selectInterval .js-chart-click[data-value="${targetValue}"]`);
    if (!option) return { opened: true, selected: false, reason: "option_not_found" };
    const text = option.textContent?.replace(/\s+/g, " ").trim() ?? null;
    option.click();
    return {
      opened: true,
      selected: true,
      target_value: targetValue,
      target_text: text,
      option_tag: option.tagName,
      option_class: typeof option.className === "string" ? option.className : null,
    };
  }, value);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }

  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  const profile = config.profiles.find((item) => item.id === "desktop_broadband");
  if (!profile || config.target_url !== "https://tradernet.ru/charts/MICEXINDEXCF") {
    throw new Error("Unexpected audit configuration");
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
  const pendingBodies = [];
  page.on("response", (response) => {
    if (!response.url().includes("getHloc")) return;
    const observation = {
      status: response.status(),
      url: response.url(),
      shape: requestShape(response.url()),
      observed_at: new Date().toISOString(),
      body_analysis: null,
      body_error: null,
    };
    observations.push(observation);
    pendingBodies.push(
      (async () => {
        try {
          const json = await response.json();
          observation.body_analysis = analyzeHloc(json, config.ticker);
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
  await Promise.allSettled(pendingBodies);
  const before = await chartState(page);
  await page.screenshot({ path: path.join(args["output-dir"], "before-D1.png"), fullPage: true });

  const action = await clickExactInterval(page, "H1");
  const transitionDeadline = Date.now() + 35_000;
  while (!observations.some((item) => item.shape?.interval === "H1") && Date.now() < transitionDeadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  await new Promise((resolve) => setTimeout(resolve, 3000));
  await Promise.allSettled(pendingBodies);

  const after = await chartState(page);
  await page.screenshot({ path: path.join(args["output-dir"], "after-H1.png"), fullPage: true });

  const d1 = observations.find((item) => item.shape?.interval === "D1") ?? null;
  const h1 = observations.find((item) => item.shape?.interval === "H1") ?? null;
  const h1IntegrityPass = Boolean(
    h1?.body_analysis &&
    h1.body_analysis.candle_count > 0 &&
    h1.body_analysis.violations.length === 0
  );

  let verdict;
  if (navigationError) verdict = "EVIDENCE_FAILURE";
  else if (!before.chart_visible) verdict = "INITIAL_CHART_NOT_VISIBLE";
  else if (!action.opened || !action.selected) verdict = "EXACT_INTERVAL_CONTROL_FAILED";
  else if (!h1) verdict = "UI_CHANGED_WITHOUT_H1_REQUEST";
  else if (h1.shape?.timeframe === d1?.shape?.timeframe) verdict = "TIMEFRAME_DID_NOT_CHANGE";
  else if (after.selected_value !== "H1" || !after.chart_visible) verdict = "UI_REQUEST_STATE_DIVERGENCE";
  else if (!h1IntegrityPass) verdict = "H1_DATA_INTEGRITY_WARN";
  else verdict = "TRANSITION_PASS";

  const result = {
    schema_version: "liminalqa-chart-timeframe-transition-v2",
    target_url: config.target_url,
    ticker: config.ticker,
    verdict,
    navigation_error: navigationError,
    before,
    action,
    after,
    d1_observation: d1,
    h1_observation: h1,
    all_get_hloc_observations: observations,
    generated_at: new Date().toISOString(),
  };

  await fs.writeFile(
    path.join(args["output-dir"], "timeframe-transition-result.json"),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8"
  );
  const lines = [
    "# Tradernet chart interval transition",
    "",
    `**Verdict:** ${verdict}  `,
    `**UI:** ${before.selected_value ?? "n/a"} → ${after.selected_value ?? "n/a"}  `,
    `**Requests observed:** ${observations.length}`,
    "",
    "| Phase | Timeframe | Interval | Candles | Violations | Status |",
    "|---|---:|---|---:|---:|---:|",
    `| Initial | ${d1?.shape?.timeframe ?? "n/a"} | ${d1?.shape?.interval ?? "n/a"} | ${d1?.body_analysis?.candle_count ?? 0} | ${d1?.body_analysis?.violations.length ?? "n/a"} | ${d1?.status ?? "n/a"} |`,
    `| After switch | ${h1?.shape?.timeframe ?? "n/a"} | ${h1?.shape?.interval ?? "n/a"} | ${h1?.body_analysis?.candle_count ?? 0} | ${h1?.body_analysis?.violations.length ?? "n/a"} | ${h1?.status ?? "n/a"} |`,
    "",
    "> The audit clicked exactly one public UI control and only observed the requests naturally initiated by that interaction.",
    "",
  ];
  await fs.writeFile(
    path.join(args["output-dir"], "timeframe-transition-summary.md"),
    lines.join("\n"),
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
