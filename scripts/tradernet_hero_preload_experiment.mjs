#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    }
    args[key.slice(2)] = value;
  }
  return args;
}

function median(values) {
  const clean = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (clean.length === 0) return null;
  const middle = Math.floor(clean.length / 2);
  return clean.length % 2 === 0
    ? (clean[middle - 1] + clean[middle]) / 2
    : clean[middle];
}

function round(value, digits = 3) {
  if (!Number.isFinite(value)) return null;
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function summarize(runs) {
  const keys = [
    "first_contentful_paint_ms",
    "largest_contentful_paint_ms",
    "hero_request_start_ms",
    "hero_response_end_ms",
    "hero_load_to_lcp_gap_ms",
    "long_task_total_ms",
    "script_transfer_bytes",
    "script_request_count",
    "navigation_response_end_ms",
  ];
  return Object.fromEntries(
    keys.map((key) => [key, round(median(runs.map((run) => run.metrics[key])))])
  );
}

function effect(baseline, treatment, key) {
  const base = baseline[key];
  const treated = treatment[key];
  if (!Number.isFinite(base) || !Number.isFinite(treated)) {
    return { treatment_minus_baseline: null, improvement_percent: null };
  }
  const difference = treated - base;
  const improvement = base === 0 ? null : ((base - treated) / base) * 100;
  return {
    treatment_minus_baseline: round(difference),
    improvement_percent: round(improvement, 2),
  };
}

async function injectPreload(request, heroUrl, userAgent) {
  const response = await fetch(request.url(), {
    redirect: "follow",
    headers: {
      "user-agent": userAgent,
      accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "accept-language": "ru-RU,ru;q=0.9,en;q=0.7",
    },
  });
  if (!response.ok) {
    throw new Error(`Document fetch returned ${response.status}`);
  }
  const original = await response.text();
  const preload = `<link rel="preload" as="image" href="${heroUrl}" fetchpriority="high" data-liminalqa="hero-preload">`;
  const modified = original.includes("<head>")
    ? original.replace("<head>", `<head>${preload}`)
    : `${preload}${original}`;

  const headers = Object.fromEntries(response.headers.entries());
  for (const header of [
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
  ]) {
    delete headers[header];
  }
  headers["content-type"] = "text/html; charset=utf-8";

  await request.respond({
    status: response.status,
    headers,
    body: modified,
  });
}

async function runVariant(browser, experiment, variantId, roundIndex, outputDir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  const userAgent =
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36";

  await page.setUserAgent(userAgent);
  await page.setViewport({ width: 412, height: 823, deviceScaleFactor: 2.625, isMobile: true });
  await page.setCacheEnabled(false);

  const client = await page.createCDPSession();
  await client.send("Network.enable");
  await client.send("Network.setCacheDisabled", { cacheDisabled: true });
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: 210_000,
    uploadThroughput: 95_000,
    connectionType: "cellular3g",
  });
  await client.send("Emulation.setCPUThrottlingRate", { rate: 4 });

  await page.evaluateOnNewDocument(() => {
    window.__liminalqa = {
      largestContentfulPaint: null,
      longTasks: [],
    };

    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        window.__liminalqa.largestContentfulPaint = {
          startTime: entry.startTime,
          renderTime: entry.renderTime,
          loadTime: entry.loadTime,
          size: entry.size,
          url: entry.url || null,
          elementTag: entry.element?.tagName || null,
          elementClass: entry.element?.className || null,
        };
      }
    }).observe({ type: "largest-contentful-paint", buffered: true });

    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        window.__liminalqa.longTasks.push({
          startTime: entry.startTime,
          duration: entry.duration,
        });
      }
    }).observe({ type: "longtask", buffered: true });
  });

  let interceptionError = null;
  if (variantId === "hero_preload") {
    await page.setRequestInterception(true);
    let documentHandled = false;
    page.on("request", async (request) => {
      try {
        const isMainDocument =
          !documentHandled && request.isNavigationRequest() && request.frame() === page.mainFrame();
        if (isMainDocument) {
          documentHandled = true;
          await injectPreload(request, experiment.hero_url, userAgent);
        } else {
          await request.continue();
        }
      } catch (error) {
        interceptionError = String(error?.stack || error);
        try {
          await request.abort("failed");
        } catch {
          // The request may already be resolved.
        }
      }
    });
  }

  const startedAt = new Date().toISOString();
  let navigationError = null;
  try {
    await page.goto(experiment.target_url, { waitUntil: "load", timeout: 90_000 });
    await new Promise((resolve) => setTimeout(resolve, 15_000));
  } catch (error) {
    navigationError = String(error?.stack || error);
  }

  const metrics = await page.evaluate((heroUrl) => {
    const paintEntries = performance.getEntriesByType("paint");
    const fcp = paintEntries.find((entry) => entry.name === "first-contentful-paint");
    const navigation = performance.getEntriesByType("navigation")[0];
    const resources = performance.getEntriesByType("resource");
    const hero = resources.find((entry) => entry.name === heroUrl);
    const scripts = resources.filter(
      (entry) => entry.initiatorType === "script" || /\.js(?:\?|$)/i.test(entry.name)
    );
    const longTasks = window.__liminalqa?.longTasks || [];
    const lcp = window.__liminalqa?.largestContentfulPaint;
    const scriptTransfer = scripts.reduce(
      (sum, entry) => sum + (Number.isFinite(entry.transferSize) ? entry.transferSize : 0),
      0
    );
    const longTaskTotal = longTasks.reduce((sum, entry) => sum + entry.duration, 0);
    const lcpTime = lcp?.startTime ?? null;
    const heroEnd = hero?.responseEnd ?? null;

    return {
      first_contentful_paint_ms: fcp?.startTime ?? null,
      largest_contentful_paint_ms: lcpTime,
      hero_request_start_ms: hero?.startTime ?? null,
      hero_response_end_ms: heroEnd,
      hero_load_to_lcp_gap_ms:
        Number.isFinite(lcpTime) && Number.isFinite(heroEnd) ? lcpTime - heroEnd : null,
      long_task_total_ms: longTaskTotal,
      script_transfer_bytes: scriptTransfer,
      script_request_count: scripts.length,
      navigation_response_end_ms: navigation?.responseEnd ?? null,
      navigation_dom_content_loaded_ms: navigation?.domContentLoadedEventEnd ?? null,
      navigation_load_event_ms: navigation?.loadEventEnd ?? null,
      lcp_entry: lcp || null,
      hero_entry: hero
        ? {
            name: hero.name,
            initiatorType: hero.initiatorType,
            startTime: hero.startTime,
            responseEnd: hero.responseEnd,
            duration: hero.duration,
            transferSize: hero.transferSize,
            encodedBodySize: hero.encodedBodySize,
          }
        : null,
      preload_present: Boolean(
        document.querySelector('link[data-liminalqa="hero-preload"]')
      ),
    };
  }, experiment.hero_url);

  const result = {
    schema_version: "liminalqa-browser-run-v1",
    variant: variantId,
    round: roundIndex,
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    target_url: experiment.target_url,
    hero_url: experiment.hero_url,
    navigation_error: navigationError,
    interception_error: interceptionError,
    metrics: Object.fromEntries(
      Object.entries(metrics).map(([key, value]) => [
        key,
        typeof value === "number" ? round(value) : value,
      ])
    ),
  };

  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(
    path.join(outputDir, `${variantId}-round-${roundIndex}.json`),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8"
  );
  await context.close();
  return result;
}

function renderMarkdown(packet) {
  const baseline = packet.variants.baseline.medians;
  const preload = packet.variants.hero_preload.medians;
  const effects = packet.effects;
  const rows = [
    ["Hero request start", "hero_request_start_ms", "ms"],
    ["Hero response end", "hero_response_end_ms", "ms"],
    ["LCP", "largest_contentful_paint_ms", "ms"],
    ["Hero loaded → LCP gap", "hero_load_to_lcp_gap_ms", "ms"],
    ["FCP", "first_contentful_paint_ms", "ms"],
    ["Long-task total", "long_task_total_ms", "ms"],
    ["Script transfer", "script_transfer_bytes", "bytes"],
    ["Script requests", "script_request_count", "count"],
  ];
  const lines = [
    "# LiminalQA · Tradernet hero preload counterfactual",
    "",
    `**Verdict:** ${packet.verdict}  `,
    `**Confidence:** ${packet.confidence}  `,
    `**Runs:** ${packet.variants.baseline.run_count} + ${packet.variants.hero_preload.run_count}`,
    "",
    "## Median metrics",
    "",
    "| Metric | Baseline | Browser-local preload | Treatment − baseline | Improvement |",
    "|---|---:|---:|---:|---:|",
  ];
  for (const [label, key, unit] of rows) {
    const effectRow = effects[key];
    const suffix = unit === "count" ? "" : ` ${unit}`;
    lines.push(
      `| ${label} | ${baseline[key] ?? "n/a"}${suffix} | ${preload[key] ?? "n/a"}${suffix} | ` +
        `${effectRow.treatment_minus_baseline ?? "n/a"}${suffix} | ` +
        `${effectRow.improvement_percent ?? "n/a"}% |`
    );
  }
  lines.push(
    "",
    "## Causal reading",
    "",
    packet.interpretation,
    "",
    "> Browser-local synthetic estimate only. It does not change Tradernet servers or prove deployed production performance.",
    ""
  );
  return lines.join("\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const required = ["experiment", "chrome", "output-dir"];
  for (const key of required) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }

  const experiment = JSON.parse(await fs.readFile(args.experiment, "utf8"));
  const runs = Number(experiment.runs_per_variant);
  if (runs !== 3) throw new Error(`Expected exactly 3 runs per variant, got ${runs}`);

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });

  const byVariant = { baseline: [], hero_preload: [] };
  try {
    for (let roundIndex = 1; roundIndex <= runs; roundIndex += 1) {
      byVariant.baseline.push(
        await runVariant(browser, experiment, "baseline", roundIndex, args["output-dir"])
      );
      byVariant.hero_preload.push(
        await runVariant(browser, experiment, "hero_preload", roundIndex, args["output-dir"])
      );
    }
  } finally {
    await browser.close();
  }

  for (const [variant, variantRuns] of Object.entries(byVariant)) {
    const failed = variantRuns.filter(
      (run) => run.navigation_error || run.interception_error || !run.metrics.largest_contentful_paint_ms
    );
    if (failed.length > 0) {
      throw new Error(`${variant} produced ${failed.length} invalid runs`);
    }
    if (variant === "hero_preload" && variantRuns.some((run) => !run.metrics.preload_present)) {
      throw new Error("Preload marker was not present in every treatment run");
    }
  }

  const baseline = summarize(byVariant.baseline);
  const preload = summarize(byVariant.hero_preload);
  const metricKeys = Object.keys(baseline);
  const effects = Object.fromEntries(metricKeys.map((key) => [key, effect(baseline, preload, key)]));
  const heroStartGain = baseline.hero_request_start_ms - preload.hero_request_start_ms;
  const lcpGain = baseline.largest_contentful_paint_ms - preload.largest_contentful_paint_ms;
  const heroEndGain = baseline.hero_response_end_ms - preload.hero_response_end_ms;

  let verdict;
  let interpretation;
  if (heroStartGain >= 500 && lcpGain >= 500) {
    verdict = "SUPPORTED";
    interpretation =
      `The local preload starts the hero ${round(heroStartGain)} ms earlier and improves LCP by ` +
      `${round(lcpGain)} ms. Late resource discovery is a material contributor in this synthetic model.`;
  } else if (heroStartGain >= 500 && lcpGain < 300) {
    verdict = "NETWORK_SUPPORTED_RENDER_NOT_IMPROVED";
    interpretation =
      `The local preload starts the hero ${round(heroStartGain)} ms earlier and finishes it ` +
      `${round(heroEndGain)} ms earlier, but LCP improves by only ${round(lcpGain)} ms. ` +
      "This shifts causal weight from network discovery to render, hydration, or visibility timing.";
  } else {
    verdict = "NOT_SUPPORTED";
    interpretation =
      "The browser-local preload did not materially advance the hero request, so this experiment does not support late discovery as the primary cause.";
  }

  const packet = {
    schema_version: "liminalqa-browser-counterfactual-result-v1",
    experiment,
    verdict,
    confidence: "MEDIUM",
    variants: {
      baseline: { run_count: byVariant.baseline.length, medians: baseline, runs: byVariant.baseline },
      hero_preload: {
        run_count: byVariant.hero_preload.length,
        medians: preload,
        runs: byVariant.hero_preload,
      },
    },
    effects,
    interpretation,
    boundaries: experiment.boundaries,
    generated_at: new Date().toISOString(),
  };

  const resultDir = path.join(args["output-dir"], "result");
  await fs.mkdir(resultDir, { recursive: true });
  await fs.writeFile(
    path.join(resultDir, "hero-preload-result.json"),
    `${JSON.stringify(packet, null, 2)}\n`,
    "utf8"
  );
  await fs.writeFile(
    path.join(resultDir, "hero-preload-summary.md"),
    renderMarkdown(packet),
    "utf8"
  );
  console.log(JSON.stringify({ verdict, baseline, preload, effects }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
