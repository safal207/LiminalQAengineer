#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    }
    result[key.slice(2)] = value;
  }
  return result;
}

function round(value, digits = 3) {
  if (!Number.isFinite(value)) return null;
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function median(values) {
  const clean = values.filter(Number.isFinite).sort((left, right) => left - right);
  if (clean.length === 0) return null;
  const middle = Math.floor(clean.length / 2);
  return clean.length % 2 === 0
    ? (clean[middle - 1] + clean[middle]) / 2
    : clean[middle];
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

function compare(baseline, treatment, key) {
  const left = baseline[key];
  const right = treatment[key];
  if (!Number.isFinite(left) || !Number.isFinite(right)) {
    return { treatment_minus_baseline: null, improvement_percent: null };
  }
  return {
    treatment_minus_baseline: round(right - left),
    improvement_percent: left === 0 ? null : round(((left - right) / left) * 100, 2),
  };
}

function defaultMobileProfile() {
  return {
    id: "mobile_3g",
    user_agent:
      "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    viewport: {
      width: 412,
      height: 823,
      deviceScaleFactor: 2.625,
      isMobile: true,
      hasTouch: true,
    },
    network: {
      latency_ms: 150,
      download_bytes_per_second: 210000,
      upload_bytes_per_second: 95000,
      connection_type: "cellular3g",
    },
    cpu_throttling_rate: 4,
    observation_ms: 15000,
  };
}

function resolveRuntimeProfile(experiment) {
  const profile = experiment.runtime_profile || defaultMobileProfile();
  const viewport = profile.viewport || {};
  const network = profile.network || {};
  const requiredNumbers = [
    ["viewport.width", viewport.width],
    ["viewport.height", viewport.height],
    ["viewport.deviceScaleFactor", viewport.deviceScaleFactor],
    ["network.latency_ms", network.latency_ms],
    ["network.download_bytes_per_second", network.download_bytes_per_second],
    ["network.upload_bytes_per_second", network.upload_bytes_per_second],
    ["cpu_throttling_rate", profile.cpu_throttling_rate],
    ["observation_ms", profile.observation_ms],
  ];
  for (const [label, value] of requiredNumbers) {
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`Invalid runtime profile field ${label}: ${value}`);
    }
  }
  if (!profile.id || !profile.user_agent || !network.connection_type) {
    throw new Error("Runtime profile requires id, user_agent, and connection_type");
  }
  return {
    ...profile,
    viewport: {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: viewport.deviceScaleFactor,
      isMobile: Boolean(viewport.isMobile),
      hasTouch: Boolean(viewport.hasTouch),
    },
    network: {
      latency_ms: network.latency_ms,
      download_bytes_per_second: network.download_bytes_per_second,
      upload_bytes_per_second: network.upload_bytes_per_second,
      connection_type: network.connection_type,
    },
  };
}

async function installPerformanceObservers(page) {
  await page.evaluateOnNewDocument(() => {
    window.__liminalqa = { largestContentfulPaint: null, longTasks: [] };
    try {
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
    } catch (error) {
      window.__liminalqa.lcpObserverError = String(error);
    }
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__liminalqa.longTasks.push({
            startTime: entry.startTime,
            duration: entry.duration,
          });
        }
      }).observe({ type: "longtask", buffered: true });
    } catch (error) {
      window.__liminalqa.longTaskObserverError = String(error);
    }
  });
}

async function enableResponseStagePreload(client, targetUrl, heroUrl) {
  const state = { fulfilled: 0, error: null };
  const target = new URL(targetUrl);
  await client.send("Fetch.enable", {
    patterns: [
      {
        urlPattern: `${target.origin}/*`,
        resourceType: "Document",
        requestStage: "Response",
      },
    ],
  });

  client.on("Fetch.requestPaused", async (event) => {
    try {
      const isTarget = event.request.url === targetUrl && Number.isInteger(event.responseStatusCode);
      if (!isTarget) {
        await client.send("Fetch.continueRequest", { requestId: event.requestId });
        return;
      }

      const responseBody = await client.send("Fetch.getResponseBody", {
        requestId: event.requestId,
      });
      const original = Buffer.from(
        responseBody.body,
        responseBody.base64Encoded ? "base64" : "utf8"
      ).toString("utf8");
      const preload =
        `<link rel="preload" as="image" href="${heroUrl}" ` +
        'fetchpriority="high" data-liminalqa="hero-preload">';
      const modified = original.includes("<head>")
        ? original.replace("<head>", `<head>${preload}`)
        : `${preload}${original}`;

      const blockedHeaders = new Set([
        "content-length",
        "content-encoding",
        "transfer-encoding",
        "connection",
        "content-md5",
      ]);
      const responseHeaders = (event.responseHeaders || []).filter(
        (header) => !blockedHeaders.has(header.name.toLowerCase())
      );
      responseHeaders.push({ name: "content-type", value: "text/html; charset=utf-8" });

      await client.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: event.responseStatusCode,
        responseHeaders,
        body: Buffer.from(modified, "utf8").toString("base64"),
      });
      state.fulfilled += 1;
    } catch (error) {
      state.error = String(error?.stack || error);
      try {
        await client.send("Fetch.continueRequest", { requestId: event.requestId });
      } catch {
        // The paused request may already be resolved.
      }
    }
  });

  return state;
}

async function collectMetrics(page, heroUrl) {
  return page.evaluate((expectedHeroUrl) => {
    const paints = performance.getEntriesByType("paint");
    const fcp = paints.find((entry) => entry.name === "first-contentful-paint");
    const navigation = performance.getEntriesByType("navigation")[0];
    const resources = performance.getEntriesByType("resource");
    const hero = resources.find((entry) => entry.name === expectedHeroUrl);
    const scripts = resources.filter(
      (entry) => entry.initiatorType === "script" || /\.js(?:\?|$)/i.test(entry.name)
    );
    const lcp = window.__liminalqa?.largestContentfulPaint || null;
    const longTasks = window.__liminalqa?.longTasks || [];
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
      preload_present: Boolean(
        document.querySelector('link[data-liminalqa="hero-preload"]')
      ),
      lcp_entry: lcp,
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
      observer_errors: {
        lcp: window.__liminalqa?.lcpObserverError || null,
        long_task: window.__liminalqa?.longTaskObserverError || null,
      },
    };
  }, heroUrl);
}

async function runVariant(browser, experiment, profile, variant, roundIndex, outputDir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();

  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.setCacheEnabled(false);
  await installPerformanceObservers(page);

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
  await client.send("Emulation.setCPUThrottlingRate", {
    rate: profile.cpu_throttling_rate,
  });

  const injectionState =
    variant === "hero_preload"
      ? await enableResponseStagePreload(client, experiment.target_url, experiment.hero_url)
      : { fulfilled: 0, error: null };

  let navigationError = null;
  const startedAt = new Date().toISOString();
  try {
    await page.goto(experiment.target_url, { waitUntil: "load", timeout: 90000 });
    await new Promise((resolve) => setTimeout(resolve, profile.observation_ms));
  } catch (error) {
    navigationError = String(error?.stack || error);
  }

  const metrics = await collectMetrics(page, experiment.hero_url);
  const result = {
    schema_version: "liminalqa-browser-run-v2",
    variant,
    round: roundIndex,
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    target_url: experiment.target_url,
    hero_url: experiment.hero_url,
    runtime_profile: profile,
    navigation_error: navigationError,
    injection: {
      fulfilled_documents: injectionState.fulfilled,
      error: injectionState.error,
      method: variant === "hero_preload" ? "cdp_response_stage" : "none",
    },
    metrics: Object.fromEntries(
      Object.entries(metrics).map(([key, value]) => [
        key,
        typeof value === "number" ? round(value) : value,
      ])
    ),
  };

  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(
    path.join(outputDir, `${variant}-round-${roundIndex}.json`),
    `${JSON.stringify(result, null, 2)}\n`,
    "utf8"
  );
  await context.close();
  return result;
}

function renderMarkdown(packet) {
  const baseline = packet.variants.baseline.medians;
  const preload = packet.variants.hero_preload.medians;
  const labels = {
    hero_request_start_ms: "Hero request start (ms)",
    hero_response_end_ms: "Hero response end (ms)",
    largest_contentful_paint_ms: "LCP (ms)",
    hero_load_to_lcp_gap_ms: "Hero loaded → LCP gap (ms)",
    first_contentful_paint_ms: "FCP (ms)",
    long_task_total_ms: "Long-task total (ms)",
    script_transfer_bytes: "Script transfer (bytes)",
    script_request_count: "Script requests",
  };
  const lines = [
    `# LiminalQA · ${packet.experiment.name}`,
    "",
    `**Runtime profile:** ${packet.runtime_profile.id}  `,
    `**Verdict:** ${packet.verdict}  `,
    `**Confidence:** ${packet.confidence}  `,
    `**Runs:** ${packet.variants.baseline.run_count} + ${packet.variants.hero_preload.run_count}`,
    "",
    "| Metric | Baseline | Browser-local preload | Treatment − baseline | Improvement |",
    "|---|---:|---:|---:|---:|",
  ];
  for (const [key, label] of Object.entries(labels)) {
    const current = packet.effects[key];
    lines.push(
      `| ${label} | ${baseline[key] ?? "n/a"} | ${preload[key] ?? "n/a"} | ` +
        `${current.treatment_minus_baseline ?? "n/a"} | ${current.improvement_percent ?? "n/a"}% |`
    );
  }
  lines.push(
    "",
    "## Causal reading",
    "",
    packet.interpretation,
    "",
    "> Browser-local response-stage injection only. Tradernet servers and persistent state are unchanged.",
    ""
  );
  return lines.join("\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["experiment", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }

  const experiment = JSON.parse(await fs.readFile(args.experiment, "utf8"));
  if (experiment.runs_per_variant !== 3) {
    throw new Error(`Expected exactly 3 runs per variant, got ${experiment.runs_per_variant}`);
  }
  const profile = resolveRuntimeProfile(experiment);

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });

  const variants = { baseline: [], hero_preload: [] };
  try {
    for (let roundIndex = 1; roundIndex <= experiment.runs_per_variant; roundIndex += 1) {
      variants.baseline.push(
        await runVariant(browser, experiment, profile, "baseline", roundIndex, args["output-dir"])
      );
      variants.hero_preload.push(
        await runVariant(
          browser,
          experiment,
          profile,
          "hero_preload",
          roundIndex,
          args["output-dir"]
        )
      );
    }
  } finally {
    await browser.close();
  }

  for (const [variant, runs] of Object.entries(variants)) {
    const invalid = runs.filter(
      (run) =>
        run.navigation_error ||
        run.injection.error ||
        !Number.isFinite(run.metrics.largest_contentful_paint_ms) ||
        !Number.isFinite(run.metrics.hero_request_start_ms)
    );
    if (invalid.length > 0) throw new Error(`${variant} produced ${invalid.length} invalid runs`);
    if (
      variant === "hero_preload" &&
      runs.some(
        (run) => run.injection.fulfilled_documents !== 1 || !run.metrics.preload_present
      )
    ) {
      throw new Error("Treatment preload was not injected exactly once in every run");
    }
  }

  const baseline = summarize(variants.baseline);
  const preload = summarize(variants.hero_preload);
  const effects = Object.fromEntries(
    Object.keys(baseline).map((key) => [key, compare(baseline, preload, key)])
  );
  const heroStartGain = baseline.hero_request_start_ms - preload.hero_request_start_ms;
  const heroEndGain = baseline.hero_response_end_ms - preload.hero_response_end_ms;
  const lcpGain = baseline.largest_contentful_paint_ms - preload.largest_contentful_paint_ms;

  let verdict;
  let interpretation;
  if (heroStartGain >= 500 && lcpGain >= 500) {
    verdict = "SUPPORTED";
    interpretation =
      `The preload starts the hero ${round(heroStartGain)} ms earlier and improves LCP by ` +
      `${round(lcpGain)} ms. Late discovery is a material contributor in this synthetic model.`;
  } else if (heroStartGain >= 500 && lcpGain < 300) {
    verdict = "NETWORK_SUPPORTED_RENDER_NOT_IMPROVED";
    interpretation =
      `The preload starts the hero ${round(heroStartGain)} ms earlier and finishes it ` +
      `${round(heroEndGain)} ms earlier, but LCP improves by only ${round(lcpGain)} ms. ` +
      "The remaining bottleneck is more consistent with render, hydration, or visibility timing.";
  } else {
    verdict = "NOT_SUPPORTED";
    interpretation =
      "The response-stage preload did not materially advance the hero request, so this run does not support late discovery as the dominant cause.";
  }

  const packet = {
    schema_version: "liminalqa-browser-counterfactual-result-v2",
    experiment,
    runtime_profile: profile,
    verdict,
    confidence: "MEDIUM",
    variants: {
      baseline: { run_count: variants.baseline.length, medians: baseline, runs: variants.baseline },
      hero_preload: {
        run_count: variants.hero_preload.length,
        medians: preload,
        runs: variants.hero_preload,
      },
    },
    effects,
    interpretation,
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
  console.log(JSON.stringify({ verdict, profile: profile.id, baseline, preload, effects }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
