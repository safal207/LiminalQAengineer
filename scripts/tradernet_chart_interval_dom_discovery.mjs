#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) out[argv[i].replace(/^--/, "")] = argv[i + 1];
  return out;
}

async function main() {
  const input = args(process.argv.slice(2));
  const config = JSON.parse(await fs.readFile(input.config, "utf8"));
  const profile = config.profiles.find((item) => item.id === "desktop_broadband");
  await fs.mkdir(input["output-dir"], { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: input.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await new Promise((resolve) => setTimeout(resolve, 12_000));

  const discovery = await page.evaluate(() => {
    const trim = (value, limit = 4000) => {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      return text.length <= limit ? text : `${text.slice(0, limit)}…`;
    };
    const exact = [...document.querySelectorAll("*")].find(
      (element) => element.textContent?.replace(/\s+/g, " ").trim() === "Дневной"
    );
    const ancestors = [];
    let current = exact;
    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
      const rect = current.getBoundingClientRect();
      ancestors.push({
        depth,
        tag: current.tagName,
        id: current.id || null,
        class: typeof current.className === "string" ? current.className : null,
        role: current.getAttribute("role"),
        aria_expanded: current.getAttribute("aria-expanded"),
        data_attributes: Object.fromEntries(
          [...current.attributes]
            .filter((attribute) => attribute.name.startsWith("data-"))
            .map((attribute) => [attribute.name, attribute.value])
        ),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        outer_html: trim(current.outerHTML, 2500),
      });
    }
    const templates = [...document.querySelectorAll('script[id*="interval" i], script[id*="chart" i]')]
      .slice(0, 40)
      .map((element) => ({ id: element.id, type: element.type, content: trim(element.textContent, 8000) }));
    const related = [...document.querySelectorAll('[class*="interval" i], [id*="interval" i], [class*="dropdown" i], [class*="select" i]')]
      .slice(0, 100)
      .map((element) => ({
        tag: element.tagName,
        id: element.id || null,
        class: typeof element.className === "string" ? element.className : null,
        text: trim(element.textContent, 500),
        html: trim(element.outerHTML, 1500),
      }));
    return { ancestors, templates, related };
  });

  await fs.writeFile(
    path.join(input["output-dir"], "interval-dom-discovery.json"),
    `${JSON.stringify(discovery, null, 2)}\n`
  );
  await page.screenshot({ path: path.join(input["output-dir"], "interval-dom-page.png"), fullPage: true });
  console.log(JSON.stringify({ ancestor_count: discovery.ancestors.length, template_count: discovery.templates.length, related_count: discovery.related.length }, null, 2));
  await context.close();
  await browser.close();
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
