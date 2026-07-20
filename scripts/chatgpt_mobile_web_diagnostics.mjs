#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) args[key] = true;
    else {
      args[key] = value;
      index += 1;
    }
  }
  return args;
}

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

function safeValue(value) {
  if (typeof value === "string") return value.slice(0, 4000);
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return String(value).slice(0, 4000);
  }
}

async function serializeConsoleMessage(message, elapsedMs) {
  const values = [];
  for (const argument of message.args()) {
    try {
      values.push(safeValue(await argument.jsonValue()));
    } catch {
      values.push(argument.toString());
    }
  }
  return {
    elapsedMs,
    type: message.type(),
    text: message.text().slice(0, 4000),
    values,
    location: message.location(),
    stackTrace: message.stackTrace?.() || null,
  };
}

async function observe(browser, target, round, outputDir) {
  const page = await browser.newPage();
  await page.setUserAgent(
    "Mozilla/5.0 (Linux; Android 16; Pixel 8 Pro) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
  );
  await page.setViewport({
    width: 412,
    height: 915,
    deviceScaleFactor: 2.625,
    isMobile: true,
    hasTouch: true,
  });

  await page.evaluateOnNewDocument(() => {
    window.__lqaLifecycle = [];
    const record = (type) => window.__lqaLifecycle.push({
      type,
      timestamp: performance.now(),
      visibilityState: document.visibilityState,
    });
    document.addEventListener("visibilitychange", () => record("visibilitychange"));
    window.addEventListener("pagehide", () => record("pagehide"));
    window.addEventListener("beforeunload", () => record("beforeunload"));
    window.addEventListener("unload", () => record("unload"));
  });

  const started = Date.now();
  const elapsed = () => Date.now() - started;
  const consolePromises = [];
  const requestEvents = [];
  const pageErrors = [];

  page.on("console", (message) => {
    consolePromises.push(serializeConsoleMessage(message, elapsed()));
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ elapsedMs: elapsed(), message: String(error.message || error), stack: error.stack || null });
  });
  page.on("request", (request) => {
    if (request.url().includes("/unauth-mweb/events/")) {
      requestEvents.push({
        elapsedMs: elapsed(),
        phase: "request",
        url: request.url(),
        method: request.method(),
        resourceType: request.resourceType(),
        initiator: request.initiator?.() || null,
      });
    }
  });
  page.on("requestfinished", (request) => {
    if (request.url().includes("/unauth-mweb/events/")) {
      requestEvents.push({
        elapsedMs: elapsed(),
        phase: "finished",
        url: request.url(),
        method: request.method(),
        resourceType: request.resourceType(),
      });
    }
  });
  page.on("requestfailed", (request) => {
    if (request.url().includes("/unauth-mweb/events/")) {
      requestEvents.push({
        elapsedMs: elapsed(),
        phase: "failed",
        url: request.url(),
        method: request.method(),
        resourceType: request.resourceType(),
        failure: request.failure()?.errorText || "request failed",
      });
    }
  });
  page.on("response", (response) => {
    if (response.url().includes("/unauth-mweb/events/")) {
      requestEvents.push({
        elapsedMs: elapsed(),
        phase: "response",
        url: response.url(),
        status: response.status(),
        method: response.request().method(),
      });
    }
  });

  let status = null;
  let navigationError = null;
  try {
    const response = await page.goto(target.url, { waitUntil: "domcontentloaded", timeout: 45000 });
    status = response?.status() ?? null;
    await new Promise((resolve) => setTimeout(resolve, 15000));
  } catch (error) {
    navigationError = String(error.message || error);
  }

  const lifecycleBeforeClose = await page.evaluate(() => ({
    events: window.__lqaLifecycle || [],
    visibilityState: document.visibilityState,
    url: location.href,
    title: document.title,
    bodyText: document.body?.innerText?.replace(/\s+/g, " ").trim().slice(0, 5000) || "",
  }));
  const screenshotName = `${target.id}-round-${round}.png`;
  await page.screenshot({ path: path.join(outputDir, screenshotName), fullPage: true, captureBeyondViewport: false });
  const consoleMessages = await Promise.all(consolePromises);

  const result = {
    target: target.id,
    requestedUrl: target.url,
    round,
    status,
    navigationError,
    elapsedBeforeCloseMs: elapsed(),
    lifecycleBeforeClose,
    requestEvents,
    consoleMessages,
    pageErrors,
    screenshot: screenshotName,
  };
  await fs.writeFile(
    path.join(outputDir, `${target.id}-round-${round}.json`),
    JSON.stringify(result, null, 2),
    "utf8",
  );
  await page.close();
  return result;
}

function adjudicate(runs) {
  const homeRuns = runs.filter((run) => run.target === "home");
  const loginRuns = runs.filter((run) => run.target === "login");
  const homeAbortSummaries = homeRuns.map((run) => ({
    round: run.round,
    lifecycleEventsBeforeClose: run.lifecycleBeforeClose.events,
    failedEvents: run.requestEvents.filter((event) => event.phase === "failed"),
    completedEvents: run.requestEvents.filter((event) => event.phase === "finished" || event.phase === "response"),
  }));
  const loginErrors = loginRuns.map((run) => ({
    round: run.round,
    consoleErrors: run.consoleMessages.filter((message) => message.type === "error"),
    pageErrors: run.pageErrors,
  }));
  return {
    mobileEventLifecycle: {
      status: "HUMAN_REVIEW_REQUIRED",
      evidence: homeAbortSummaries,
      decisionRule: "An abort before any pagehide, visibilitychange, beforeunload or unload event disproves page-close teardown as the immediate trigger, but does not alone prove user harm.",
    },
    loginConsole: {
      status: "HUMAN_REVIEW_REQUIRED",
      evidence: loginErrors,
      decisionRule: "A stable message, stack and visible broken task are required before a product-defect claim.",
    },
  };
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.chrome || !args["output-dir"]) {
    throw new Error("Usage: --chrome PATH --output-dir PATH");
  }
  const outputDir = args["output-dir"];
  await fs.mkdir(outputDir, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--no-first-run"],
  });
  const targets = [
    { id: "home", url: "https://chatgpt.com/" },
    { id: "login", url: "https://chatgpt.com/auth/login" },
  ];
  const runs = [];
  try {
    for (const target of targets) {
      for (let round = 1; round <= 2; round += 1) {
        runs.push(await observe(browser, target, round, outputDir));
      }
    }
  } finally {
    await browser.close();
  }
  const packetWithoutDigest = {
    schema_version: "liminalqa-chatgpt-mobile-diagnostics-v1",
    generatedAt: new Date().toISOString(),
    boundaries: {
      publicPagesOnly: true,
      authenticatedTesting: false,
      promptSubmission: false,
      loginSubmission: false,
      directApplicationApiTesting: false,
      accessControlBypass: false,
    },
    runs,
    adjudication: adjudicate(runs),
    verdict: "HUMAN_REVIEW_REQUIRED",
  };
  const digest = sha256(JSON.stringify(packetWithoutDigest));
  const packet = { ...packetWithoutDigest, evidenceSha256: digest };
  await fs.writeFile(path.join(outputDir, "diagnostic-result.json"), JSON.stringify(packet, null, 2), "utf8");
  console.log(JSON.stringify({ evidenceSha256: digest, adjudication: packet.adjudication }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
