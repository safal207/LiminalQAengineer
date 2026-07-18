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
  await page.setUserAgent(variant.user_agent);
  await page.setViewport(variant.viewport);
  await page.setCacheEnabled(false);

  let documentStatus = null;
  let navigationError = null;
  const response = await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 90_000 }).catch((error) => {
    navigationError = String(error?.stack || error);
    return null;
  });
  documentStatus = response?.status() ?? null;
  await new Promise((resolve) => setTimeout(resolve, 12_000));

  const dom = await page.evaluate(() => {
    const bodyText = document.body?.innerText || "";
    const surfaces = [...document.querySelectorAll('canvas, svg, [id*="chart" i], [class*="chart" i]')]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          tag: element.tagName,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          visible: rect.width >= 120 && rect.height >= 80 && style.display !== "none" && style.visibility !== "hidden",
        };
      });
    return {
      title: document.title,
      final_url: location.href,
      has_404_text: /404\s*ERROR|Страница не найдена|page not found/i.test(bodyText),
      has_chart_surface: surfaces.some((surface) => surface.visible),
      surface_count: surfaces.length,
      body_excerpt: bodyText.replace(/\s+/g, " ").trim().slice(0, 500),
    };
  });

  await page.screenshot({ path: path.join(outputDir, `${variant.id}.png`), fullPage: true });
  const result = {
    id: variant.id,
    user_agent_family: variant.user_agent_family,
    viewport_family: variant.viewport_family,
    document_status: documentStatus,
    navigation_error: navigationError,
    ...dom,
  };
  await fs.writeFile(path.join(outputDir, `${variant.id}.json`), `${JSON.stringify(result, null, 2)}\n`);
  await context.close();
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  const desktop = config.profiles.find((profile) => profile.id === "desktop_broadband");
  const mobile = config.profiles.find((profile) => profile.id === "mobile_4g");
  if (!desktop || !mobile) throw new Error("Required profiles are missing");

  const variants = [
    {
      id: "desktop_ua_desktop_viewport",
      user_agent_family: "desktop",
      viewport_family: "desktop",
      user_agent: desktop.user_agent,
      viewport: desktop.viewport,
    },
    {
      id: "desktop_ua_mobile_viewport",
      user_agent_family: "desktop",
      viewport_family: "mobile",
      user_agent: desktop.user_agent,
      viewport: mobile.viewport,
    },
    {
      id: "mobile_ua_desktop_viewport",
      user_agent_family: "mobile",
      viewport_family: "desktop",
      user_agent: mobile.user_agent,
      viewport: desktop.viewport,
    },
    {
      id: "mobile_ua_mobile_viewport",
      user_agent_family: "mobile",
      viewport_family: "mobile",
      user_agent: mobile.user_agent,
      viewport: mobile.viewport,
    },
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
      results.push(await runVariant(browser, config.target_url, variant, args["output-dir"]));
    }
  } finally {
    await browser.close();
  }

  const mobileUaResults = results.filter((result) => result.user_agent_family === "mobile");
  const desktopUaResults = results.filter((result) => result.user_agent_family === "desktop");
  const mobileUaAlways404 = mobileUaResults.every(
    (result) => result.document_status === 404 || result.has_404_text
  );
  const desktopUaAlwaysWorks = desktopUaResults.every(
    (result) => result.document_status === 200 && result.has_chart_surface
  );
  const verdict = mobileUaAlways404 && desktopUaAlwaysWorks
    ? "USER_AGENT_ROUTING_CONFIRMED"
    : results.some((result) => result.document_status === 404 || result.has_404_text)
      ? "MIXED_ROUTE_FAILURE"
      : "NOT_REPRODUCED";

  const packet = {
    schema_version: "liminalqa-public-route-matrix-result-v1",
    target_url: config.target_url,
    verdict,
    results,
    interpretation:
      verdict === "USER_AGENT_ROUTING_CONFIRMED"
        ? "The public chart route succeeds for the desktop user-agent at both viewport sizes and returns the 404 experience for the mobile user-agent at both viewport sizes. The dominant cause is server/client routing by user-agent rather than responsive viewport width."
        : "The four-way matrix did not isolate a pure user-agent branch; inspect the individual results.",
    generated_at: new Date().toISOString(),
  };
  await fs.writeFile(
    path.join(args["output-dir"], "route-matrix-result.json"),
    `${JSON.stringify(packet, null, 2)}\n`,
    "utf8"
  );
  const lines = [
    "# Tradernet public chart route matrix",
    "",
    `**Verdict:** ${verdict}`,
    "",
    "| Variant | Document status | 404 experience | Chart surface |",
    "|---|---:|---:|---:|",
    ...results.map(
      (result) =>
        `| ${result.id} | ${result.document_status ?? "n/a"} | ${result.has_404_text ? "yes" : "no"} | ${result.has_chart_surface ? "yes" : "no"} |`
    ),
    "",
    packet.interpretation,
    "",
  ];
  await fs.writeFile(path.join(args["output-dir"], "route-matrix-summary.md"), lines.join("\n"));
  console.log(JSON.stringify(packet, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
