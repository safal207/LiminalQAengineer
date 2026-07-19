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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  const profile = config.profiles.find((item) => item.id === "mobile_4g");
  if (!profile || config.target_url !== "https://tradernet.ru/terminal") {
    throw new Error("Unexpected bounded configuration");
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
  await client.send("Emulation.setCPUThrottlingRate", { rate: profile.cpu_throttling_rate });

  const resources = new Map();
  client.on("Network.requestWillBeSent", (event) => {
    resources.set(event.requestId, {
      url: event.request.url,
      type: event.type || null,
      status: null,
      encoded_bytes: null,
    });
  });
  client.on("Network.responseReceived", (event) => {
    const item = resources.get(event.requestId);
    if (!item) return;
    item.status = event.response.status;
    item.mime_type = event.response.mimeType;
  });
  client.on("Network.loadingFinished", (event) => {
    const item = resources.get(event.requestId);
    if (item) item.encoded_bytes = event.encodedDataLength;
  });

  const response = await page.goto(config.target_url, {
    waitUntil: "domcontentloaded",
    timeout: 90_000,
  });
  await new Promise((resolve) => setTimeout(resolve, 12_000));

  const images = await page.evaluate(() =>
    [...document.images].map((image) => {
      const rect = image.getBoundingClientRect();
      const style = getComputedStyle(image);
      const visible =
        rect.width > 1 &&
        rect.height > 1 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0;
      const inViewport =
        rect.bottom > 0 &&
        rect.right > 0 &&
        rect.top < innerHeight &&
        rect.left < innerWidth;
      return {
        src: image.getAttribute("src"),
        current_src: image.currentSrc || null,
        alt: image.alt || null,
        natural_width: image.naturalWidth,
        natural_height: image.naturalHeight,
        rendered_width: rect.width,
        rendered_height: rect.height,
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        visible,
        in_viewport: inViewport,
        loading: image.loading || null,
        fetch_priority: image.fetchPriority || null,
      };
    })
  );

  const byUrl = new Map();
  for (const item of resources.values()) {
    if (!byUrl.has(item.url) || (item.encoded_bytes || 0) > (byUrl.get(item.url).encoded_bytes || 0)) {
      byUrl.set(item.url, item);
    }
  }
  const enriched = images.map((image) => {
    const resource = byUrl.get(image.current_src) || byUrl.get(image.src) || null;
    return {
      ...image,
      network_status: resource?.status ?? null,
      encoded_bytes: resource?.encoded_bytes ?? null,
    };
  });
  const loadedInvisible = enriched
    .filter((image) => image.natural_width > 0 && !image.visible && (image.encoded_bytes || 0) > 0)
    .sort((left, right) => (right.encoded_bytes || 0) - (left.encoded_bytes || 0));
  const broken = enriched.filter((image) => image.natural_width === 0);
  const invisibleBytes = loadedInvisible.reduce((sum, image) => sum + (image.encoded_bytes || 0), 0);
  const verdict = invisibleBytes >= 100_000 ? "HIDDEN_ASSET_WASTE" : broken.length > 0 ? "BROKEN_IMAGE_REFERENCE" : "NO_MATERIAL_HIDDEN_IMAGE_WASTE";

  const result = {
    schema_version: "liminalqa-terminal-image-visibility-v1",
    target_url: config.target_url,
    profile: profile.id,
    navigation_status: response?.status() ?? null,
    verdict,
    image_count: enriched.length,
    loaded_invisible_image_count: loadedInvisible.length,
    loaded_invisible_encoded_bytes: invisibleBytes,
    broken_image_count: broken.length,
    loaded_invisible_images: loadedInvisible,
    broken_images: broken,
    images: enriched,
    generated_at: new Date().toISOString(),
  };

  await page.screenshot({ path: path.join(args["output-dir"], "mobile-terminal.png"), fullPage: true });
  await fs.writeFile(
    path.join(args["output-dir"], "terminal-image-visibility-result.json"),
    `${JSON.stringify(result, null, 2)}\n`
  );
  const lines = [
    "# Tradernet mobile terminal image visibility",
    "",
    `**Verdict:** ${verdict}  `,
    `**Loaded but invisible images:** ${loadedInvisible.length}  `,
    `**Invisible encoded transfer:** ${invisibleBytes} bytes  `,
    `**Broken image elements:** ${broken.length}`,
    "",
    "| Current source | Visible | In viewport | Rendered size | Natural size | Transfer | HTTP |",
    "|---|---:|---:|---:|---:|---:|---:|",
    ...enriched.map((image) =>
      `| ${image.current_src || image.src || "n/a"} | ${image.visible} | ${image.in_viewport} | ${Math.round(image.rendered_width)}×${Math.round(image.rendered_height)} | ${image.natural_width}×${image.natural_height} | ${image.encoded_bytes ?? "n/a"} | ${image.network_status ?? "n/a"} |`
    ),
    "",
    "> The probe performs one passive public mobile navigation. It does not authenticate, submit forms, access account data or call application APIs directly.",
    "",
  ];
  await fs.writeFile(path.join(args["output-dir"], "terminal-image-visibility-summary.md"), lines.join("\n"));

  await context.close();
  await browser.close();
  console.log(JSON.stringify({ verdict, invisibleBytes, loadedInvisible: loadedInvisible.length, broken: broken.length }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
