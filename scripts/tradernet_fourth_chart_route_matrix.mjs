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
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key}`);
    args[key.slice(2)] = value;
  }
  return args;
}

async function runVariant(browser, targetUrl, variant, outputDir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(variant.userAgent);
  await page.setViewport(variant.viewport);
  await page.setCacheEnabled(false);

  let navigationError = null;
  const response = await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 90_000 }).catch((error) => {
    navigationError = String(error?.stack || error);
    return null;
  });
  await new Promise((resolve) => setTimeout(resolve, 12_000));

  const dom = await page.evaluate(() => {
    const text = document.body?.innerText || "";
    const surfaces = [...document.querySelectorAll('canvas, svg, [id*="chart" i], [class*="chart" i]')].map((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        visible: rect.width >= 120 && rect.height >= 80 && style.display !== "none" && style.visibility !== "hidden",
      };
    });
    return {
      title: document.title,
      final_url: location.href,
      has_404_text: /404\s*ERROR|Страница не найдена|page not found/i.test(text),
      has_chart_surface: surfaces.some((surface) => surface.visible),
      body_excerpt: text.replace(/\s+/g, " ").trim().slice(0, 500),
    };
  });

  await page.screenshot({ path: path.join(outputDir, `${variant.id}.png`), fullPage: true });
  const result = {
    id: variant.id,
    user_agent_family: variant.userAgentFamily,
    viewport_family: variant.viewportFamily,
    document_status: response?.status() ?? null,
    navigation_error: navigationError,
    ...dom,
  };
  await fs.writeFile(path.join(outputDir, `${variant.id}.json`), `${JSON.stringify(result, null, 2)}\n`);
  await context.close();
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }

  const targetUrl = "https://tradernet.ru/charts/MICEXINDEXCF";
  const desktopUserAgent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";
  const mobileUserAgent = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36";
  const desktopViewport = { width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false };
  const mobileViewport = { width: 412, height: 823, deviceScaleFactor: 2.625, isMobile: true, hasTouch: true };
  const variants = [
    { id: "desktop_ua_desktop_viewport", userAgentFamily: "desktop", viewportFamily: "desktop", userAgent: desktopUserAgent, viewport: desktopViewport },
    { id: "desktop_ua_mobile_viewport", userAgentFamily: "desktop", viewportFamily: "mobile", userAgent: desktopUserAgent, viewport: mobileViewport },
    { id: "mobile_ua_desktop_viewport", userAgentFamily: "mobile", viewportFamily: "desktop", userAgent: mobileUserAgent, viewport: desktopViewport },
    { id: "mobile_ua_mobile_viewport", userAgentFamily: "mobile", viewportFamily: "mobile", userAgent: mobileUserAgent, viewport: mobileViewport },
  ];

  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });
  const results = [];
  try {
    for (const variant of variants) {
      results.push(await runVariant(browser, targetUrl, variant, args["output-dir"]));
    }
  } finally {
    await browser.close();
  }

  const mobile = results.filter((item) => item.user_agent_family === "mobile");
  const desktop = results.filter((item) => item.user_agent_family === "desktop");
  const mobileAlways404 = mobile.every((item) => item.document_status === 404 || item.has_404_text);
  const desktopAlwaysWorks = desktop.every((item) => item.document_status === 200 && item.has_chart_surface);
  const allWork = results.every((item) => item.document_status === 200 && item.has_chart_surface && !item.has_404_text);
  const verdict = mobileAlways404 && desktopAlwaysWorks
    ? "USER_AGENT_ROUTING_CONFIRMED"
    : allWork
      ? "NOT_REPRODUCED"
      : results.some((item) => item.document_status === 404 || item.has_404_text || item.navigation_error)
        ? "MIXED_ROUTE_FAILURE"
        : "INCONCLUSIVE";

  const packet = {
    schema_version: "liminalqa-public-route-matrix-result-v2",
    target_url: targetUrl,
    verdict,
    results,
    generated_at: new Date().toISOString(),
  };
  await fs.writeFile(path.join(args["output-dir"], "route-matrix-result.json"), `${JSON.stringify(packet, null, 2)}\n`);
  const markdown = [
    "# Tradernet fourth chart-route matrix",
    "",
    `**Verdict:** ${verdict}`,
    "",
    "| Variant | HTTP | 404 | Chart |",
    "|---|---:|---:|---:|",
    ...results.map((item) => `| ${item.id} | ${item.document_status ?? "n/a"} | ${item.has_404_text ? "yes" : "no"} | ${item.has_chart_surface ? "yes" : "no"} |`),
    "",
  ].join("\n");
  await fs.writeFile(path.join(args["output-dir"], "route-matrix-summary.md"), markdown);
  console.log(JSON.stringify(packet, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
