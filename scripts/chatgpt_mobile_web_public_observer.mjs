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
    if (!value || value.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = value;
      index += 1;
    }
  }
  return args;
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function normalizeText(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function isFirstParty(rawUrl) {
  try {
    const host = new URL(rawUrl).hostname.toLowerCase();
    return (
      host === "chatgpt.com" ||
      host.endsWith(".chatgpt.com") ||
      host === "openai.com" ||
      host.endsWith(".openai.com") ||
      host === "oaistatic.com" ||
      host.endsWith(".oaistatic.com") ||
      host === "oaiusercontent.com" ||
      host.endsWith(".oaiusercontent.com")
    );
  } catch {
    return false;
  }
}

function duplicateValues(values) {
  const counts = new Map();
  for (const value of values.map(normalizeText).filter(Boolean)) {
    const key = value.toLocaleLowerCase("en-US");
    counts.set(key, { text: value, count: (counts.get(key)?.count ?? 0) + 1 });
  }
  return [...counts.values()].filter((item) => item.count > 1);
}

function stableSubset(value) {
  return JSON.parse(JSON.stringify(value));
}

async function installObservers(page) {
  await page.evaluateOnNewDocument(() => {
    window.__liminalqa = {
      cls: 0,
      layoutShifts: [],
      longTasks: [],
      runtimeErrors: [],
      unhandledRejections: [],
    };

    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) {
            window.__liminalqa.cls += entry.value;
            window.__liminalqa.layoutShifts.push({
              value: entry.value,
              startTime: entry.startTime,
            });
          }
        }
      }).observe({ type: "layout-shift", buffered: true });
    } catch {}

    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__liminalqa.longTasks.push({
            duration: entry.duration,
            startTime: entry.startTime,
            name: entry.name,
          });
        }
      }).observe({ type: "longtask", buffered: true });
    } catch {}

    window.addEventListener("error", (event) => {
      window.__liminalqa.runtimeErrors.push({
        message: String(event.message || "runtime error"),
        filename: String(event.filename || ""),
        lineno: event.lineno || 0,
        colno: event.colno || 0,
      });
    });

    window.addEventListener("unhandledrejection", (event) => {
      window.__liminalqa.unhandledRejections.push({
        reason: String(event.reason?.message || event.reason || "unhandled rejection"),
      });
    });
  });
}

async function inspectDocument(page, minimumTouchTarget) {
  return page.evaluate((minimumTarget) => {
    const normalize = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        style.opacity !== "0" &&
        element.getAttribute("aria-hidden") !== "true" &&
        rect.width > 0 &&
        rect.height > 0 &&
        rect.bottom > 0 &&
        rect.right > 0 &&
        rect.top < innerHeight &&
        rect.left < innerWidth
      );
    };
    const accessibleName = (element) => normalize(
      element.getAttribute("aria-label") ||
      element.getAttribute("title") ||
      element.getAttribute("placeholder") ||
      element.innerText ||
      element.textContent ||
      element.getAttribute("name") ||
      element.id
    );
    const rectRecord = (element) => {
      const rect = element.getBoundingClientRect();
      return {
        x: Math.round(rect.x * 100) / 100,
        y: Math.round(rect.y * 100) / 100,
        width: Math.round(rect.width * 100) / 100,
        height: Math.round(rect.height * 100) / 100,
        right: Math.round(rect.right * 100) / 100,
        bottom: Math.round(rect.bottom * 100) / 100,
      };
    };

    const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6,[role='heading']")]
      .filter(visible)
      .map((element) => ({
        text: accessibleName(element),
        tag: element.tagName.toLowerCase(),
        level: element.getAttribute("aria-level") || element.tagName.slice(1) || null,
        rect: rectRecord(element),
      }))
      .filter((item) => item.text);

    const interactiveSelector = [
      "button",
      "a[href]",
      "input:not([type='hidden'])",
      "textarea",
      "select",
      "[role='button']",
      "[role='link']",
      "[contenteditable='true']",
      "[tabindex]:not([tabindex='-1'])",
    ].join(",");

    const seen = new Set();
    const interactives = [...document.querySelectorAll(interactiveSelector)]
      .filter((element) => {
        if (!visible(element) || seen.has(element)) return false;
        seen.add(element);
        return true;
      })
      .map((element) => {
        const rect = rectRecord(element);
        return {
          name: accessibleName(element),
          tag: element.tagName.toLowerCase(),
          role: element.getAttribute("role") || null,
          type: element.getAttribute("type") || null,
          rect,
          targetTooSmall: rect.width < minimumTarget || rect.height < minimumTarget,
        };
      });

    const fixedOrSticky = [...document.querySelectorAll("body *")]
      .filter((element) => {
        if (!visible(element)) return false;
        const position = getComputedStyle(element).position;
        return position === "fixed" || position === "sticky";
      })
      .slice(0, 120)
      .map((element) => ({
        name: accessibleName(element).slice(0, 180),
        tag: element.tagName.toLowerCase(),
        position: getComputedStyle(element).position,
        zIndex: getComputedStyle(element).zIndex,
        rect: rectRecord(element),
      }));

    const composerCandidates = [...document.querySelectorAll("textarea,[contenteditable='true'],form")]
      .filter(visible)
      .map((element) => ({
        name: accessibleName(element).slice(0, 180),
        tag: element.tagName.toLowerCase(),
        rect: rectRecord(element),
      }));

    const overlapPairs = [];
    for (const composer of composerCandidates) {
      for (const overlay of fixedOrSticky) {
        const a = composer.rect;
        const b = overlay.rect;
        const overlapWidth = Math.max(0, Math.min(a.right, b.right) - Math.max(a.x, b.x));
        const overlapHeight = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y));
        const area = overlapWidth * overlapHeight;
        if (area > 16 && !(composer.tag === overlay.tag && composer.name === overlay.name)) {
          overlapPairs.push({ composer, overlay, overlapArea: Math.round(area) });
        }
      }
    }

    const nav = performance.getEntriesByType("navigation")[0];
    const resources = performance.getEntriesByType("resource");
    const liminal = window.__liminalqa || {};

    return {
      title: document.title,
      language: document.documentElement.lang || null,
      bodyText: normalize(document.body?.innerText || "").slice(0, 30000),
      viewport: {
        innerWidth,
        innerHeight,
        visualViewportWidth: window.visualViewport?.width || null,
        visualViewportHeight: window.visualViewport?.height || null,
        documentWidth: document.documentElement.scrollWidth,
        documentHeight: document.documentElement.scrollHeight,
        horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      },
      headings,
      interactives,
      fixedOrSticky,
      composerCandidates,
      overlapPairs,
      semanticCounts: {
        landmarks: document.querySelectorAll("main,nav,aside,header,footer,[role='main'],[role='navigation'],[role='complementary'],[role='banner'],[role='contentinfo']").length,
        dialogs: document.querySelectorAll("dialog,[role='dialog'],[role='alertdialog']").length,
        liveRegions: document.querySelectorAll("[aria-live]").length,
        forms: document.forms.length,
      },
      performance: nav ? {
        domContentLoaded: nav.domContentLoadedEventEnd,
        loadEvent: nav.loadEventEnd,
        responseStart: nav.responseStart,
        responseEnd: nav.responseEnd,
        transferSize: nav.transferSize,
        encodedBodySize: nav.encodedBodySize,
        decodedBodySize: nav.decodedBodySize,
      } : null,
      resourceSummary: {
        count: resources.length,
        transferSize: resources.reduce((sum, item) => sum + (item.transferSize || 0), 0),
        encodedBodySize: resources.reduce((sum, item) => sum + (item.encodedBodySize || 0), 0),
        initiatorCounts: resources.reduce((acc, item) => {
          const key = item.initiatorType || "other";
          acc[key] = (acc[key] || 0) + 1;
          return acc;
        }, {}),
      },
      webVitals: {
        cls: liminal.cls || 0,
        layoutShifts: liminal.layoutShifts || [],
        longTasks: liminal.longTasks || [],
      },
      runtimeErrors: liminal.runtimeErrors || [],
      unhandledRejections: liminal.unhandledRejections || [],
    };
  }, minimumTouchTarget);
}

async function captureFocusOrder(page, maximum = 18) {
  const order = [];
  await page.evaluate(() => document.body?.focus());
  for (let index = 0; index < maximum; index += 1) {
    await page.keyboard.press("Tab");
    const item = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const normalize = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName.toLowerCase(),
        name: normalize(
          element.getAttribute("aria-label") ||
          element.getAttribute("title") ||
          element.getAttribute("placeholder") ||
          element.innerText ||
          element.textContent ||
          element.getAttribute("name") ||
          element.id
        ).slice(0, 220),
        role: element.getAttribute("role") || null,
        visible: rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      };
    });
    if (!item) break;
    order.push(item);
  }
  return order;
}

async function observePage(browser, config, profile, target, round, outputDir) {
  const page = await browser.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await installObservers(page);

  const consoleMessages = [];
  const pageErrors = [];
  const failedRequests = [];
  const errorResponses = [];

  page.on("console", (message) => {
    consoleMessages.push({ type: message.type(), text: message.text().slice(0, 2000) });
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ message: String(error.message || error).slice(0, 2000) });
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
      failure: request.failure()?.errorText || "request failed",
      firstParty: isFirstParty(request.url()),
    });
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      errorResponses.push({
        url: response.url(),
        status: response.status(),
        resourceType: response.request().resourceType(),
        firstParty: isFirstParty(response.url()),
      });
    }
  });

  let mainResponse = null;
  let navigationError = null;
  const startedAt = new Date().toISOString();
  try {
    mainResponse = await page.goto(target.url, {
      waitUntil: "domcontentloaded",
      timeout: 45000,
    });
    await new Promise((resolve) => setTimeout(resolve, config.observation_ms));
  } catch (error) {
    navigationError = String(error.message || error);
  }

  const safeId = `${profile.id}-${target.id}-round-${round}`;
  await fs.mkdir(outputDir, { recursive: true });
  const screenshotPath = path.join(outputDir, `${safeId}.png`);
  try {
    await page.screenshot({ path: screenshotPath, fullPage: true, captureBeyondViewport: false });
  } catch {}

  let inspection = null;
  let accessibility = null;
  let focusOrder = [];
  try {
    inspection = await inspectDocument(page, config.thresholds.minimum_touch_target_css_px);
    focusOrder = await captureFocusOrder(page);
    try {
      accessibility = await page.accessibility.snapshot({ interestingOnly: false });
    } catch (error) {
      accessibility = { unavailable: String(error.message || error) };
    }
  } catch (error) {
    inspection = { inspectionError: String(error.message || error) };
  }

  const result = {
    profile: profile.id,
    target: target.id,
    round,
    startedAt,
    requestedUrl: target.url,
    finalUrl: page.url(),
    status: mainResponse?.status() ?? null,
    navigationError,
    inspection,
    focusOrder,
    accessibility,
    consoleMessages,
    pageErrors,
    failedRequests,
    errorResponses,
    screenshot: path.basename(screenshotPath),
  };

  await fs.writeFile(
    path.join(outputDir, `${safeId}.json`),
    JSON.stringify(result, null, 2),
    "utf8",
  );
  await page.close();
  return result;
}

function deriveObservations(config, runs) {
  const observations = [];
  for (const run of runs) {
    const inspection = run.inspection || {};
    const headings = inspection.headings?.map((item) => item.text) || [];
    const duplicateHeadings = duplicateValues(headings);
    const smallTargets = inspection.interactives?.filter((item) => item.targetTooSmall) || [];
    const consoleErrors = run.consoleMessages.filter((item) => item.type === "error");
    const firstPartyFailures = run.failedRequests.filter((item) => item.firstParty);
    const firstPartyErrorResponses = run.errorResponses.filter((item) => item.firstParty);

    if ((inspection.viewport?.horizontalOverflow || 0) > config.thresholds.maximum_horizontal_overflow_css_px) {
      observations.push({
        id: "horizontal-overflow",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED",
        value: inspection.viewport.horizontalOverflow,
      });
    }
    if (duplicateHeadings.length) {
      observations.push({
        id: "duplicate-visible-headings",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED",
        values: duplicateHeadings,
      });
    }
    if (smallTargets.length) {
      observations.push({
        id: "small-visible-interactive-targets",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED_NOT_AUTOMATIC_FAILURE",
        count: smallTargets.length,
        examples: smallTargets.slice(0, 20),
      });
    }
    if (inspection.overlapPairs?.length) {
      observations.push({
        id: "composer-fixed-element-overlap",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED_NEEDS_SCREENSHOT_REVIEW",
        count: inspection.overlapPairs.length,
        examples: inspection.overlapPairs.slice(0, 12),
      });
    }
    if (consoleErrors.length || run.pageErrors.length || inspection.runtimeErrors?.length || inspection.unhandledRejections?.length) {
      observations.push({
        id: "runtime-errors",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED_USER_IMPACT_UNKNOWN",
        consoleErrors,
        pageErrors: run.pageErrors,
        runtimeErrors: inspection.runtimeErrors || [],
        unhandledRejections: inspection.unhandledRejections || [],
      });
    }
    if (firstPartyFailures.length || firstPartyErrorResponses.length) {
      observations.push({
        id: "first-party-request-failures",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED_USER_IMPACT_UNKNOWN",
        failedRequests: firstPartyFailures,
        errorResponses: firstPartyErrorResponses,
      });
    }
    if (run.status && run.status >= 400) {
      observations.push({
        id: "main-document-error-status",
        profile: run.profile,
        target: run.target,
        round: run.round,
        status: "OBSERVED",
        value: run.status,
      });
    }
  }

  const byKey = new Map();
  for (const observation of observations) {
    const key = `${observation.id}|${observation.profile}|${observation.target}`;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(observation);
  }
  const repeated = [];
  for (const [key, values] of byKey.entries()) {
    if (values.length >= 2) {
      repeated.push({
        key,
        id: values[0].id,
        profile: values[0].profile,
        target: values[0].target,
        repeatedRounds: values.length,
        status: "REPEATED_OBSERVATION",
      });
    }
  }

  const routeMatrix = runs
    .filter((run) => run.target === "home" && run.round === 1)
    .map((run) => ({
      profile: run.profile,
      status: run.status,
      finalUrl: run.finalUrl,
      title: run.inspection?.title || null,
      bodyDigest: sha256(run.inspection?.bodyText || ""),
    }));

  return { observations, repeated, routeMatrix };
}

function renderSummary(config, runs, derived, digest) {
  const lines = [];
  lines.push("# ChatGPT public mobile-web audit");
  lines.push("");
  lines.push(`Case: \`${config.case_id}\``);
  lines.push(`Evidence SHA-256: \`${digest}\``);
  lines.push("");
  lines.push("## Boundary");
  lines.push("");
  lines.push("Public signed-out pages only. No login submission, prompt submission, file upload, permissions, direct application API testing, access-control bypass, fuzzing, load testing, or private data collection.");
  lines.push("");
  lines.push("## Route matrix");
  lines.push("");
  lines.push("| Profile | HTTP | Final URL | Title |");
  lines.push("|---|---:|---|---|");
  for (const item of derived.routeMatrix) {
    lines.push(`| ${item.profile} | ${item.status ?? "n/a"} | ${item.finalUrl} | ${normalizeText(item.title)} |`);
  }
  lines.push("");
  lines.push("## Repeated observations");
  lines.push("");
  if (!derived.repeated.length) {
    lines.push("No detector signal repeated in both rounds. This is not a product-pass verdict.");
  } else {
    for (const item of derived.repeated) {
      lines.push(`- \`${item.id}\` on \`${item.profile}\` / \`${item.target}\`: ${item.repeatedRounds} rounds.`);
    }
  }
  lines.push("");
  lines.push("## Per-run snapshot");
  lines.push("");
  lines.push("| Profile | Target | Round | Overflow px | Visible headings | Small targets | Console/page errors | First-party failures | CLS |");
  lines.push("|---|---|---:|---:|---:|---:|---:|---:|---:|");
  for (const run of runs) {
    const inspection = run.inspection || {};
    const errorCount = run.consoleMessages.filter((item) => item.type === "error").length + run.pageErrors.length + (inspection.runtimeErrors?.length || 0) + (inspection.unhandledRejections?.length || 0);
    const failureCount = run.failedRequests.filter((item) => item.firstParty).length + run.errorResponses.filter((item) => item.firstParty).length;
    lines.push(`| ${run.profile} | ${run.target} | ${run.round} | ${inspection.viewport?.horizontalOverflow ?? "n/a"} | ${inspection.headings?.length ?? "n/a"} | ${inspection.interactives?.filter((item) => item.targetTooSmall).length ?? "n/a"} | ${errorCount} | ${failureCount} | ${Number(inspection.webVitals?.cls || 0).toFixed(4)} |`);
  }
  lines.push("");
  lines.push("## Interpretation rule");
  lines.push("");
  lines.push("A repeated detector signal is evidence for human review, not automatic proof of user harm. Authenticated chat history, message composition, long conversations, streaming, attachments, voice, images, Projects, Work, account menus, billing and settings remain outside this packet.");
  return `${lines.join("\n")}\n`;
}

async function main() {
  const args = parseArgs(process.argv);
  const configPath = args.config;
  const chromePath = args.chrome;
  const outputDir = args["output-dir"];
  if (!configPath || !chromePath || !outputDir) {
    throw new Error("Usage: --config PATH --chrome PATH --output-dir PATH");
  }

  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  if (config.target_url !== "https://chatgpt.com/") {
    throw new Error("The bounded target must be https://chatgpt.com/");
  }
  const boundaries = config.boundaries || {};
  const requiredFalse = [
    "authenticated_testing",
    "message_submission",
    "login_submission",
    "file_upload",
    "microphone_permission",
    "camera_permission",
    "direct_application_api_testing",
    "fuzzing",
    "load_testing",
    "active_security_testing",
    "captcha_or_access_control_bypass",
    "private_data_collection",
  ];
  if (boundaries.public_pages_only !== true || requiredFalse.some((key) => boundaries[key] !== false)) {
    throw new Error("Safety boundary validation failed");
  }

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-background-networking",
      "--disable-default-apps",
      "--disable-extensions",
      "--no-first-run",
    ],
  });

  const rawDir = path.join(outputDir, "raw");
  await fs.mkdir(rawDir, { recursive: true });
  const targets = [
    { id: "home", url: config.target_url },
    { id: "login", url: config.login_url },
  ];
  const runs = [];
  try {
    for (const profile of config.profiles) {
      for (const target of targets) {
        if (target.id === "login" && !profile.id.startsWith("mobile-ua-mobile")) continue;
        for (let round = 1; round <= 2; round += 1) {
          runs.push(await observePage(browser, config, profile, target, round, rawDir));
        }
      }
    }
  } finally {
    await browser.close();
  }

  const derived = deriveObservations(config, runs);
  const packetWithoutDigest = {
    schema_version: config.schema_version,
    case_id: config.case_id,
    generated_at: new Date().toISOString(),
    target: config.target_url,
    boundaries: stableSubset(config.boundaries),
    thresholds: stableSubset(config.thresholds),
    profiles: stableSubset(config.profiles.map((profile) => ({ id: profile.id, viewport: profile.viewport }))),
    runs,
    derived,
    verdict: "HUMAN_REVIEW_REQUIRED",
    verdict_meaning: "Review repeated public detector signals. Do not infer authenticated mobile-chat defects from signed-out evidence.",
  };
  const canonical = JSON.stringify(packetWithoutDigest);
  const digest = sha256(canonical);
  const packet = { ...packetWithoutDigest, evidence_sha256: digest };
  await fs.writeFile(path.join(outputDir, "chatgpt-mobile-web-result.json"), JSON.stringify(packet, null, 2), "utf8");
  await fs.writeFile(path.join(outputDir, "chatgpt-mobile-web-summary.md"), renderSummary(config, runs, derived, digest), "utf8");
  console.log(JSON.stringify({ digest, repeated: derived.repeated, routeMatrix: derived.routeMatrix }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
