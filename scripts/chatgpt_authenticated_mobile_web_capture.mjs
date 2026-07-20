#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const args = {
    browserUrl: "http://127.0.0.1:9222",
    config: "audits/chatgpt/authenticated-mobile-web-capture-v1.json",
    outputDir: "reports/chatgpt-authenticated-mobile-web",
    pageIndex: null,
    includeScreenshots: false,
    acknowledgePrivateScreenshotRisk: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--browser-url") args.browserUrl = argv[++index];
    else if (value === "--config") args.config = argv[++index];
    else if (value === "--output-dir") args.outputDir = argv[++index];
    else if (value === "--page-index") args.pageIndex = Number(argv[++index]);
    else if (value === "--include-screenshots") args.includeScreenshots = true;
    else if (value === "--acknowledge-private-screenshot-risk") args.acknowledgePrivateScreenshotRisk = true;
    else if (value === "--help") {
      console.log(`Usage:
  node scripts/chatgpt_authenticated_mobile_web_capture.mjs [options]

Options:
  --browser-url URL        Existing Chrome DevTools endpoint (default http://127.0.0.1:9222)
  --config PATH            Capture contract JSON
  --output-dir PATH        Local evidence directory
  --page-index N           Select one chatgpt.com tab when more than one is attached
  --include-screenshots    Capture globally text-redacted screenshots
  --acknowledge-private-screenshot-risk
                           Required together with --include-screenshots
`);
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${value}`);
    }
  }
  return args;
}

function sha256(value) {
  return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function nowIso() {
  return new Date().toISOString();
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function originMatches(rawUrl, targetOrigin) {
  try {
    return new URL(rawUrl).origin === targetOrigin;
  } catch {
    return false;
  }
}

function publicPageDescriptor(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    return {
      origin: parsed.origin,
      path_sha256: sha256(parsed.pathname),
      path_length: parsed.pathname.length,
      has_query: Boolean(parsed.search),
      has_fragment: Boolean(parsed.hash),
    };
  } catch {
    return { origin: "invalid", path_sha256: sha256("invalid"), path_length: 0, has_query: false, has_fragment: false };
  }
}

function safeLocation(rawUrl, targetOrigin) {
  try {
    const parsed = new URL(rawUrl);
    return {
      first_party: parsed.origin === targetOrigin,
      origin: parsed.origin === targetOrigin ? targetOrigin : "third-party-redacted",
      path_sha256: sha256(parsed.pathname),
      path_length: parsed.pathname.length,
    };
  } catch {
    return { first_party: false, origin: "invalid", path_sha256: sha256("invalid"), path_length: 0 };
  }
}

async function installRuntimeObservers(page) {
  await page.evaluate(() => {
    if (window.__liminalAuthenticatedMobileWebObservers) return;
    const state = { cls: 0, longTasks: [], installedAt: Date.now() };
    window.__liminalAuthenticatedMobileWebObservers = state;

    try {
      const clsObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) state.cls += entry.value;
        }
      });
      clsObserver.observe({ type: "layout-shift", buffered: true });
    } catch {}

    try {
      const longTaskObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          state.longTasks.push({ startTime: entry.startTime, duration: entry.duration });
          if (state.longTasks.length > 100) state.longTasks.shift();
        }
      });
      longTaskObserver.observe({ type: "longtask", buffered: true });
    } catch {}
  });
}

async function signedInState(page) {
  return page.evaluate(() => {
    const visible = (element) => {
      if (!element) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    };
    const elements = [...document.querySelectorAll("a,button")].filter(visible);
    const hasVisibleLogin = elements.some((element) => {
      const name = `${element.getAttribute("aria-label") || ""} ${element.textContent || ""}`.trim().toLowerCase();
      const href = element.getAttribute("href") || "";
      return name === "log in" || name === "login" || /\/auth\/login/.test(href);
    });
    const hasConversationTurns = Boolean(document.querySelector("[data-message-author-role], [data-testid^='conversation-turn'], article"));
    const hasAccountSurface = elements.some((element) => {
      const name = `${element.getAttribute("aria-label") || ""} ${element.getAttribute("title") || ""}`.toLowerCase();
      return /account|profile|workspace|settings/.test(name);
    });
    const hasHistorySurface = Boolean(document.querySelector("nav, aside, [data-testid*='sidebar'], [aria-label*='history' i]"));
    return {
      has_visible_login_control: hasVisibleLogin,
      has_conversation_turns: hasConversationTurns,
      has_account_surface: hasAccountSurface,
      has_history_surface: hasHistorySurface,
      signed_in_likely: !hasVisibleLogin && (hasConversationTurns || hasAccountSurface || hasHistorySurface || location.pathname.startsWith("/c/")),
    };
  });
}

async function capturePageState(page, checkpointId) {
  return page.evaluate(async (checkpoint) => {
    const visible = (element) => {
      if (!element) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    };
    const rectOf = (element) => {
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return {
        x: Math.round(rect.x * 10) / 10,
        y: Math.round(rect.y * 10) / 10,
        width: Math.round(rect.width * 10) / 10,
        height: Math.round(rect.height * 10) / 10,
        right: Math.round(rect.right * 10) / 10,
        bottom: Math.round(rect.bottom * 10) / 10,
      };
    };
    const digest = async (text) => {
      const bytes = new TextEncoder().encode(String(text || ""));
      const hash = await crypto.subtle.digest("SHA-256", bytes);
      return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    };
    const canonicalControl = (rawName) => {
      const name = String(rawName || "").trim().replace(/\s+/g, " ").toLowerCase();
      const rules = [
        ["sidebar", /sidebar|menu|history/],
        ["login", /^log in$|^login$/],
        ["send", /send message|^send$/],
        ["stop", /stop generating|stop response|^stop$/],
        ["regenerate", /regenerate|try again/],
        ["attachment", /attach|add files|upload/],
        ["dictation", /dictation|microphone|voice/],
        ["model", /model|gpt-/],
        ["account", /account|profile|workspace|settings/],
        ["search", /search/],
        ["new-chat", /new chat/],
        ["share", /share/],
        ["copy", /copy/],
        ["sources", /source|citation/],
        ["scroll-latest", /latest|bottom/],
        ["continue", /^continue$/],
        ["close", /^close$|dismiss/],
        ["more", /^more$|more options/],
      ];
      for (const [canonical, pattern] of rules) if (pattern.test(name)) return canonical;
      return null;
    };

    const controls = [];
    for (const element of [...document.querySelectorAll("button,a,input,[role='button'],[role='menuitem'],[role='tab']")].filter(visible).slice(0, 300)) {
      const rawName = element.getAttribute("aria-label") || element.getAttribute("title") || element.getAttribute("name") || element.textContent || "";
      const canonical = canonicalControl(rawName);
      controls.push({
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role"),
        type: element.getAttribute("type"),
        canonical_name: canonical,
        unknown_name_sha256: canonical ? null : await digest(rawName),
        unknown_name_length: canonical ? 0 : String(rawName).trim().length,
        rect: rectOf(element),
        disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
      });
    }

    const messageCandidates = [...document.querySelectorAll("[data-message-author-role], [data-testid^='conversation-turn'], article")].filter(visible);
    const seen = new Set();
    const messages = [];
    for (const element of messageCandidates) {
      if (seen.has(element)) continue;
      seen.add(element);
      const text = element.innerText || "";
      const role = element.getAttribute("data-message-author-role") || element.getAttribute("data-role") || "unknown";
      messages.push({
        role: ["user", "assistant", "system", "tool"].includes(role) ? role : "unknown",
        text_length: text.length,
        text_sha256: await digest(text),
        rect: rectOf(element),
      });
    }

    const composerCandidates = [...document.querySelectorAll("textarea,[contenteditable='true']")].filter(visible);
    composerCandidates.sort((left, right) => {
      const a = left.getBoundingClientRect();
      const b = right.getBoundingClientRect();
      return (b.bottom + b.width * b.height / 10000) - (a.bottom + a.width * a.height / 10000);
    });
    const composer = composerCandidates[0] || null;
    const composerText = composer ? (composer.value ?? composer.innerText ?? "") : "";

    const fixedSticky = [...document.querySelectorAll("body *")].filter((element) => {
      if (!visible(element)) return false;
      const position = getComputedStyle(element).position;
      return position === "fixed" || position === "sticky";
    }).slice(0, 120).map((element) => ({
      tag: element.tagName.toLowerCase(),
      position: getComputedStyle(element).position,
      rect: rectOf(element),
    }));

    const scrollables = [...document.querySelectorAll("body *")].filter((element) => {
      if (!visible(element)) return false;
      const style = getComputedStyle(element);
      return /(auto|scroll)/.test(style.overflowY) && element.scrollHeight > element.clientHeight + 20;
    }).sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)).slice(0, 8).map((element) => ({
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role"),
      rect: rectOf(element),
      scroll_top: Math.round(element.scrollTop),
      scroll_height: Math.round(element.scrollHeight),
      client_height: Math.round(element.clientHeight),
      distance_to_bottom: Math.round(element.scrollHeight - element.clientHeight - element.scrollTop),
    }));

    const active = document.activeElement;
    const activeRawName = active ? (active.getAttribute("aria-label") || active.getAttribute("title") || active.getAttribute("name") || "") : "";
    const activeCanonical = canonicalControl(activeRawName);
    const state = window.__liminalAuthenticatedMobileWebObservers || { cls: null, longTasks: [] };
    const vv = window.visualViewport;
    const visualViewport = vv ? {
      width: vv.width,
      height: vv.height,
      offset_left: vv.offsetLeft,
      offset_top: vv.offsetTop,
      page_left: vv.pageLeft,
      page_top: vv.pageTop,
      scale: vv.scale,
    } : null;

    return {
      checkpoint_id: checkpoint,
      captured_at: new Date().toISOString(),
      viewport: { inner_width: innerWidth, inner_height: innerHeight, device_pixel_ratio: devicePixelRatio },
      visual_viewport: visualViewport,
      keyboard_inferred: Boolean(vv && vv.height < innerHeight - 120),
      document: {
        scroll_width: document.documentElement.scrollWidth,
        client_width: document.documentElement.clientWidth,
        scroll_height: document.documentElement.scrollHeight,
        client_height: document.documentElement.clientHeight,
        horizontal_overflow_px: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
      },
      composer: composer ? {
        rect: rectOf(composer),
        tag: composer.tagName.toLowerCase(),
        text_length: composerText.length,
        text_sha256: await digest(composerText),
        multiline: /\n/.test(composerText),
      } : null,
      messages,
      message_count: messages.length,
      controls,
      control_count: controls.length,
      streaming_control_visible: controls.some((control) => control.canonical_name === "stop"),
      return_to_latest_visible: controls.some((control) => control.canonical_name === "scroll-latest"),
      attachment_control_visible: controls.some((control) => control.canonical_name === "attachment"),
      sidebar_candidate_visible: Boolean([...document.querySelectorAll("nav,aside,[data-testid*='sidebar']")].find(visible)),
      fixed_sticky: fixedSticky,
      scrollables: scrollables,
      active_element: active ? {
        tag: active.tagName.toLowerCase(),
        canonical_name: activeCanonical,
        unknown_name_sha256: activeCanonical ? null : await digest(activeRawName),
        unknown_name_length: activeCanonical ? 0 : activeRawName.length,
      } : null,
      performance: {
        cls_since_attach: state.cls,
        long_task_count_since_attach: state.longTasks.length,
        long_tasks_since_attach: state.longTasks.slice(-20),
      },
    };
  }, checkpointId);
}

async function captureRedactedScreenshot(page, outputPath) {
  const styleId = "liminal-private-text-redaction";
  await page.evaluate((id) => {
    document.getElementById(id)?.remove();
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      body *, body *::before, body *::after {
        color: transparent !important;
        text-shadow: none !important;
        caret-color: transparent !important;
      }
      img, svg, canvas, video, iframe {
        filter: blur(18px) !important;
      }
      input, textarea, [contenteditable='true'] {
        color: transparent !important;
        text-shadow: none !important;
      }
    `;
    document.documentElement.appendChild(style);
  }, styleId);
  try {
    await page.screenshot({ path: outputPath, fullPage: false, captureBeyondViewport: false });
  } finally {
    await page.evaluate((id) => document.getElementById(id)?.remove(), styleId);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const config = await readJson(args.config);
  const targetOrigin = config.target_origin;

  if (config.execution_mode !== "local_attached_browser_only") throw new Error("Capture contract must be local_attached_browser_only");
  if (args.includeScreenshots && !args.acknowledgePrivateScreenshotRisk) {
    throw new Error("--include-screenshots requires --acknowledge-private-screenshot-risk");
  }

  await fs.mkdir(args.outputDir, { recursive: true });
  const browser = await puppeteer.connect({ browserURL: args.browserUrl, defaultViewport: null });
  const runtime = {
    started_at: nowIso(),
    browser_url_sha256: sha256(args.browserUrl),
    console_events: [],
    page_errors: [],
    first_party_failed_requests: [],
    first_party_http_errors: [],
  };

  try {
    const candidates = (await browser.pages()).filter((page) => originMatches(page.url(), targetOrigin));
    if (candidates.length === 0) throw new Error(`No attached ${targetOrigin} tab found`);
    if (candidates.length > 1 && args.pageIndex === null) {
      throw new Error(`Found ${candidates.length} chatgpt.com tabs. Close extras or pass --page-index N.`);
    }
    const page = candidates[args.pageIndex ?? 0];
    const initialUrl = page.url();
    const auth = await signedInState(page);
    if (!auth.signed_in_likely) {
      throw new Error("Signed-in state was not established. Sign in manually in the attached browser before capture.");
    }

    page.on("console", (message) => {
      const location = message.location();
      const text = message.text();
      runtime.console_events.push({
        observed_at: nowIso(),
        type: message.type(),
        text_length: text.length,
        text_sha256: sha256(text),
        location: safeLocation(location.url || "", targetOrigin),
        line_number: location.lineNumber ?? null,
        column_number: location.columnNumber ?? null,
      });
    });
    page.on("pageerror", (error) => {
      runtime.page_errors.push({
        observed_at: nowIso(),
        name: error?.name || "Error",
        message_length: String(error?.message || "").length,
        message_sha256: sha256(error?.message || ""),
        stack_sha256: sha256(error?.stack || ""),
      });
    });
    page.on("requestfailed", (request) => {
      if (!originMatches(request.url(), targetOrigin)) return;
      runtime.first_party_failed_requests.push({
        observed_at: nowIso(),
        method: request.method(),
        resource_type: request.resourceType(),
        location: safeLocation(request.url(), targetOrigin),
        failure_text_sha256: sha256(request.failure()?.errorText || ""),
      });
    });
    page.on("response", (response) => {
      if (!originMatches(response.url(), targetOrigin) || response.status() < 400) return;
      runtime.first_party_http_errors.push({
        observed_at: nowIso(),
        status: response.status(),
        method: response.request().method(),
        resource_type: response.request().resourceType(),
        location: safeLocation(response.url(), targetOrigin),
      });
    });

    await installRuntimeObservers(page);
    const rl = readline.createInterface({ input, output });
    const captures = [];

    console.log("\nAuthenticated ChatGPT mobile-web capture is attached.");
    console.log("No clicks, typing, navigation, login or prompt submission are automated.");
    console.log("Raw message text, chat titles, credentials, cookies and request bodies are not persisted.\n");

    for (const checkpoint of config.checkpoints) {
      const answer = await rl.question(`Checkpoint ${checkpoint.id}\n${checkpoint.instruction}\nPress Enter to capture, type s to skip, or q to stop: `);
      if (answer.trim().toLowerCase() === "q") break;
      if (answer.trim().toLowerCase() === "s") {
        captures.push({ checkpoint_id: checkpoint.id, status: "skipped", captured_at: nowIso() });
        continue;
      }
      if (!originMatches(page.url(), targetOrigin)) throw new Error("Attached page left the allowed target origin");

      const state = await capturePageState(page, checkpoint.id);
      state.page = publicPageDescriptor(page.url());
      state.status = "captured";
      state.private_text_persisted = false;
      const statePath = path.join(args.outputDir, `${checkpoint.id}.json`);
      await writeJson(statePath, state);

      let screenshot = null;
      if (args.includeScreenshots) {
        screenshot = `${checkpoint.id}.redacted.png`;
        await captureRedactedScreenshot(page, path.join(args.outputDir, screenshot));
      }
      captures.push({
        checkpoint_id: checkpoint.id,
        status: "captured",
        captured_at: state.captured_at,
        evidence_file: path.basename(statePath),
        evidence_sha256: sha256(await fs.readFile(statePath)),
        screenshot,
      });
      console.log(`Captured ${checkpoint.id}.`);
    }
    rl.close();

    runtime.finished_at = nowIso();
    runtime.console_events = runtime.console_events.slice(-200);
    runtime.page_errors = runtime.page_errors.slice(-100);
    runtime.first_party_failed_requests = runtime.first_party_failed_requests.slice(-200);
    runtime.first_party_http_errors = runtime.first_party_http_errors.slice(-200);

    const manifest = {
      schema_version: config.schema_version,
      case_id: config.case_id,
      generated_at: nowIso(),
      mode: config.execution_mode,
      target_origin: targetOrigin,
      initial_page: publicPageDescriptor(initialUrl),
      signed_in_check: auth,
      boundaries: config.boundaries,
      privacy: config.privacy,
      captures,
      runtime,
      verdict: captures.some((capture) => capture.status === "captured")
        ? "AUTHENTICATED_LOCAL_EVIDENCE_CAPTURED_PENDING_ADJUDICATION"
        : "NO_AUTHENTICATED_EVIDENCE_CAPTURED",
      authority: "HUMAN_REVIEW_REQUIRED",
    };
    const manifestPath = path.join(args.outputDir, "manifest.json");
    await writeJson(manifestPath, manifest);
    console.log(`\nManifest: ${manifestPath}`);
    console.log(`Manifest SHA-256: ${sha256(await fs.readFile(manifestPath))}`);
  } finally {
    await browser.disconnect();
  }
}

main().catch((error) => {
  console.error(`Capture failed: ${error.message}`);
  process.exitCode = 1;
});
