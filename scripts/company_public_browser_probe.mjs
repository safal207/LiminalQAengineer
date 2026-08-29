#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");

const PROFILE_DEFINITIONS = {
  desktop: {
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    viewport: {
      width: 1440,
      height: 1000,
      deviceScaleFactor: 1,
      isMobile: false,
      hasTouch: false,
    },
  },
  mobile: {
    userAgent:
      "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    viewport: {
      width: 412,
      height: 915,
      deviceScaleFactor: 2.625,
      isMobile: true,
      hasTouch: true,
    },
  },
};

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

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function sanitizeUrl(rawValue) {
  try {
    const url = new URL(rawValue);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch {
    return String(rawValue || "").slice(0, 500);
  }
}

function sanitizeText(rawValue) {
  let value = String(rawValue || "");
  value = value.replace(/https:\/\/[^\s"'<>]+/gi, (candidate) => sanitizeUrl(candidate));
  value = value.replace(
    /\b(?:bearer\s+)?[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_.-]{10,}\b/gi,
    "[REDACTED_TOKEN]",
  );
  value = value.replace(
    /\b(?:token|secret|api[_-]?key|password|session)\s*[:=]\s*[^\s,;]+/gi,
    "$1=[REDACTED]",
  );
  return normalizeText(value).slice(0, 800);
}

function walkAccessibility(node, output = { nodes: 0, unnamedInteractive: 0, names: [] }) {
  if (!node) return output;
  output.nodes += 1;
  const role = String(node.role || "").toLowerCase();
  const interactiveRoles = new Set([
    "button",
    "link",
    "checkbox",
    "radio",
    "textbox",
    "combobox",
    "menuitem",
    "tab",
    "slider",
    "switch",
    "spinbutton",
  ]);
  const name = normalizeText(node.name);
  if (interactiveRoles.has(role) && !name) output.unnamedInteractive += 1;
  if (name && output.names.length < 100) output.names.push({ role, name: name.slice(0, 160) });
  for (const child of node.children || []) walkAccessibility(child, output);
  return output;
}

async function activeElementState(page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!element || element === document.body || element === document.documentElement) return null;
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const rectangle = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    let href = null;
    if (element instanceof HTMLAnchorElement && element.href) {
      try {
        const url = new URL(element.href);
        href = `${url.protocol}//${url.host}${url.pathname}`;
      } catch {
        href = null;
      }
    }
    return {
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role"),
      id: element.id || null,
      test_id:
        element.getAttribute("data-testid") ||
        element.getAttribute("data-qa-id") ||
        element.getAttribute("data-test") ||
        null,
      name: normalize(
        element.getAttribute("aria-label") ||
          element.getAttribute("title") ||
          element.getAttribute("alt") ||
          element.textContent,
      ).slice(0, 160),
      href,
      tab_index: element.tabIndex,
      visible:
        rectangle.width > 0 &&
        rectangle.height > 0 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0,
      focus_indicator: {
        outline_style: style.outlineStyle,
        outline_width: style.outlineWidth,
        box_shadow: style.boxShadow.slice(0, 240),
      },
    };
  });
}

async function keyboardTrace(page, steps) {
  await page
    .evaluate(() => {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      if (document.body instanceof HTMLElement) {
        document.body.tabIndex = -1;
        document.body.focus({ preventScroll: true });
        document.body.removeAttribute("tabindex");
      }
    })
    .catch(() => null);

  const trace = [];
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press("Tab");
    await sleep(70);
    trace.push(await activeElementState(page));
  }
  const nonNull = trace.filter(Boolean);
  const unique = [
    ...new Map(
      nonNull.map((entry) => [
        `${entry.tag}|${entry.role || ""}|${entry.id || ""}|${entry.test_id || ""}|${entry.name}|${entry.href || ""}`,
        entry,
      ]),
    ).values(),
  ];
  return {
    attempted_steps: steps,
    non_null_steps: nonNull.length,
    unique_focus_targets: unique.length,
    first_focus: nonNull[0] || null,
    skip_link_reached: nonNull.some((entry) => /skip( to)? (main|content)/i.test(entry.name || "")),
    unique_targets: unique,
    trace,
  };
}

async function inspectDom(page, retainBodySample) {
  return page.evaluate((retainSample) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const visible = (element) => {
      const rectangle = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rectangle.width > 0 &&
        rectangle.height > 0 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0
      );
    };
    const accessibleName = (element) =>
      normalize(
        element.getAttribute("aria-label") ||
          element.getAttribute("title") ||
          element.getAttribute("alt") ||
          element.textContent,
      );
    const descriptor = (element) => ({
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role"),
      id: element.id || null,
      test_id:
        element.getAttribute("data-testid") ||
        element.getAttribute("data-qa-id") ||
        element.getAttribute("data-test") ||
        null,
      tab_index: element.tabIndex,
      disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
      name: accessibleName(element).slice(0, 160),
    });

    const bodyText = normalize(document.body?.innerText || "");
    const interactiveSelector =
      "a[href], button, input, select, textarea, [role='button'], [role='link'], [role='tab'], [role='menuitem'], [role='checkbox'], [role='radio'], [role='switch'], [tabindex]";
    const interactives = [...document.querySelectorAll(interactiveSelector)].filter(visible);
    const enabled = interactives.filter(
      (element) => !element.disabled && element.getAttribute("aria-disabled") !== "true",
    );
    const sequential = enabled.filter((element) => element.tabIndex >= 0);
    const unnamedSequential = sequential.filter((element) => !accessibleName(element));

    const nestedSelector =
      "button button, button a[href], a[href] button, [role='button'] button, button [role='button'], [role='link'] button, button [role='link']";
    const nested = [...document.querySelectorAll(nestedSelector)].filter(visible);

    const ids = [...document.querySelectorAll("[id]")].map((element) => element.id).filter(Boolean);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const images = [...document.querySelectorAll("img")].filter(visible);
    const inputs = [...document.querySelectorAll("input, select, textarea")].filter(visible);
    const unlabeledInputs = inputs.filter((element) => {
      const explicitLabel = element.id
        ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`)
        : null;
      return !accessibleName(element) && !explicitLabel;
    });
    const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
      .filter(visible)
      .map((element) => ({
        level: Number(element.tagName.slice(1)),
        text: normalize(element.textContent).slice(0, 240),
      }))
      .slice(0, 80);

    return {
      title: document.title,
      html_lang: document.documentElement.lang || null,
      body_text_sha256_input: bodyText,
      body_text_length: bodyText.length,
      body_text_sample: retainSample ? bodyText.slice(0, 2000) : null,
      headings,
      landmarks: {
        main: document.querySelectorAll("main, [role='main']").length,
        navigation: document.querySelectorAll("nav, [role='navigation']").length,
        banner: document.querySelectorAll("header, [role='banner']").length,
        contentinfo: document.querySelectorAll("footer, [role='contentinfo']").length,
      },
      visible_counts: {
        interactive: interactives.length,
        enabled_interactive: enabled.length,
        sequential_focusable: sequential.length,
        buttons: [...document.querySelectorAll("button, [role='button']")].filter(visible).length,
        links: [...document.querySelectorAll("a[href], [role='link']")].filter(visible).length,
        inputs: inputs.length,
        images: images.length,
        canvas: [...document.querySelectorAll("canvas")].filter(visible).length,
        svg: [...document.querySelectorAll("svg")].filter(visible).length,
        video: [...document.querySelectorAll("video")].filter(visible).length,
        iframe: document.querySelectorAll("iframe").length,
      },
      unnamed_sequential_controls: unnamedSequential.slice(0, 50).map(descriptor),
      nested_interactive_controls: nested.slice(0, 50).map((element) => ({
        child: descriptor(element),
        parent: element.parentElement ? descriptor(element.parentElement) : null,
      })),
      duplicate_ids: duplicateIds.slice(0, 100),
      missing_alt_visible_images: images.filter((image) => !normalize(image.getAttribute("alt"))).length,
      unlabeled_visible_inputs: unlabeledInputs.slice(0, 50).map(descriptor),
      forms_present: document.querySelectorAll("form").length,
    };
  }, retainBodySample);
}

async function observe() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = args.config;
  const targetId = args["target-id"];
  const profileId = args.profile;
  const chromePath = args.chrome;
  const outputDir = args["output-dir"];
  if (!configPath || !targetId || !profileId || !chromePath || !outputDir) {
    throw new Error("Required: --config --target-id --profile --chrome --output-dir");
  }

  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  const target = config.targets.find((candidate) => candidate.id === targetId);
  if (!target) throw new Error(`Unknown target id: ${targetId}`);
  if (!config.profiles.includes(profileId) || !PROFILE_DEFINITIONS[profileId]) {
    throw new Error(`Profile is outside the validated contract: ${profileId}`);
  }
  const profile = PROFILE_DEFINITIONS[profileId];
  await fs.rm(outputDir, { recursive: true, force: true });
  await fs.mkdir(outputDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-domain-reliability",
    ],
  });

  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(90000);
  await page.setUserAgent(profile.userAgent);
  await page.setViewport(profile.viewport);

  const consoleEntries = [];
  const failedRequests = [];
  const responseStats = [];
  page.on("console", (message) => {
    if (consoleEntries.length >= 200) return;
    consoleEntries.push({ type: message.type(), text: sanitizeText(message.text()) });
  });
  page.on("requestfailed", (request) => {
    if (failedRequests.length >= 100) return;
    failedRequests.push({
      url: sanitizeUrl(request.url()),
      method: request.method(),
      resource_type: request.resourceType(),
      error: sanitizeText(request.failure()?.errorText || "unknown"),
    });
  });
  page.on("response", (response) => {
    if (responseStats.length >= 2500) return;
    responseStats.push({
      url: sanitizeUrl(response.url()),
      status: response.status(),
      resource_type: response.request().resourceType(),
    });
  });

  const startedAt = Date.now();
  let navigationResponse = null;
  let navigationError = null;
  try {
    navigationResponse = await page.goto(target.url, {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
  } catch (error) {
    navigationError = sanitizeText(error?.message || error);
  }
  await sleep(config.settings.settle_ms);
  const settledAt = Date.now();

  const dom = await inspectDom(page, config.settings.retain_body_sample);
  const bodyText = dom.body_text_sha256_input;
  delete dom.body_text_sha256_input;
  dom.body_text_sha256 = sha256(bodyText);

  const accessibilityTree = await page.accessibility.snapshot({ interestingOnly: false }).catch(() => null);
  const accessibility = walkAccessibility(accessibilityTree);
  const keyboard = await keyboardTrace(page, config.settings.keyboard_tab_steps).catch(() => ({
    attempted_steps: config.settings.keyboard_tab_steps,
    non_null_steps: 0,
    unique_focus_targets: 0,
    first_focus: null,
    skip_link_reached: false,
    unique_targets: [],
    trace: [],
  }));

  const performance = await page
    .evaluate(() => {
      const navigation = performance.getEntriesByType("navigation")[0];
      const resources = performance.getEntriesByType("resource");
      const byType = {};
      let transferSize = 0;
      let encodedBodySize = 0;
      for (const entry of resources) {
        const type = entry.initiatorType || "other";
        byType[type] = (byType[type] || 0) + 1;
        transferSize += Number(entry.transferSize || 0);
        encodedBodySize += Number(entry.encodedBodySize || 0);
      }
      return {
        navigation: navigation
          ? {
              type: navigation.type,
              response_start_ms: navigation.responseStart,
              response_end_ms: navigation.responseEnd,
              dom_content_loaded_ms: navigation.domContentLoadedEventEnd,
              load_event_ms: navigation.loadEventEnd,
              transfer_size: navigation.transferSize,
            }
          : null,
        resource_count: resources.length,
        resource_count_by_initiator: byType,
        resource_transfer_size: transferSize,
        resource_encoded_body_size: encodedBodySize,
      };
    })
    .catch(() => null);

  const redirectChain = navigationResponse
    ? navigationResponse
        .request()
        .redirectChain()
        .map((request) => sanitizeUrl(request.url()))
    : [];
  const screenshotName = "screenshot.png";
  await page
    .screenshot({ path: path.join(outputDir, screenshotName), fullPage: true })
    .catch(() => null);

  const result = {
    schema_version: "liminalqa-company-browser-result-v1",
    observed_at: new Date().toISOString(),
    company: config.company,
    target,
    profile: profileId,
    viewport: profile.viewport,
    navigation: {
      requested_url: target.url,
      final_url: sanitizeUrl(page.url()),
      status: navigationResponse?.status() ?? null,
      error: navigationError,
      redirect_chain: redirectChain,
      started_at: new Date(startedAt).toISOString(),
      settled_at: new Date(settledAt).toISOString(),
      wall_time_ms: settledAt - startedAt,
    },
    dom,
    accessibility: {
      node_count: accessibility.nodes,
      unnamed_interactive_count: accessibility.unnamedInteractive,
      named_node_sample: accessibility.names,
    },
    keyboard,
    console: {
      error_count: consoleEntries.filter((entry) => entry.type === "error").length,
      warning_count: consoleEntries.filter((entry) => entry.type === "warning").length,
      signatures: consoleEntries,
    },
    network: {
      response_count: responseStats.length,
      status_4xx_count: responseStats.filter((entry) => entry.status >= 400 && entry.status < 500).length,
      status_5xx_count: responseStats.filter((entry) => entry.status >= 500).length,
      failed_request_count: failedRequests.length,
      failed_requests: failedRequests,
      response_status_counts: responseStats.reduce((counts, entry) => {
        const key = String(entry.status);
        counts[key] = (counts[key] || 0) + 1;
        return counts;
      }, {}),
    },
    performance,
    signals: {
      sequential_focusable_count: dom.visible_counts.sequential_focusable,
      keyboard_unique_focus_targets: keyboard.unique_focus_targets,
      keyboard_focus_gap:
        config.settings.keyboard_tab_steps > 0 &&
        dom.visible_counts.sequential_focusable > 0 &&
        keyboard.unique_focus_targets === 0,
      unnamed_sequential_controls: dom.unnamed_sequential_controls.length,
      nested_interactive_controls: dom.nested_interactive_controls.length,
      unnamed_accessibility_controls: accessibility.unnamedInteractive,
      duplicate_ids: dom.duplicate_ids.length,
      missing_alt_visible_images: dom.missing_alt_visible_images,
      unlabeled_visible_inputs: dom.unlabeled_visible_inputs.length,
    },
    screenshot: screenshotName,
    boundaries: config.boundaries,
    authority: {
      mode: "evidence_only",
      grants: {
        ownership: false,
        approval: false,
        external_submission: false,
        deployment: false,
        merge: false,
      },
    },
  };

  const resultText = `${JSON.stringify(result, null, 2)}\n`;
  await fs.writeFile(path.join(outputDir, "browser-result.json"), resultText);
  const summary =
    `# Browser evidence · ${config.company.name} · ${target.id} · ${profileId}\n\n` +
    `- HTTP: ${result.navigation.status ?? "n/a"}\n` +
    `- Final URL: ${result.navigation.final_url}\n` +
    `- Sequential focusables: ${result.signals.sequential_focusable_count}\n` +
    `- Unique Tab targets: ${result.signals.keyboard_unique_focus_targets}\n` +
    `- Unnamed sequential controls: ${result.signals.unnamed_sequential_controls}\n` +
    `- Nested interactive controls: ${result.signals.nested_interactive_controls}\n` +
    `- Accessibility-tree unnamed controls: ${result.signals.unnamed_accessibility_controls}\n` +
    `- Console errors: ${result.console.error_count}\n\n` +
    `Public passive observation only; no authentication, forms, direct APIs, state changes, fuzzing, or load testing.\n`;
  await fs.writeFile(path.join(outputDir, "browser-summary.md"), summary);
  await fs.writeFile(
    path.join(outputDir, "BROWSER_SHA256SUMS.txt"),
    `${sha256(resultText)}  browser-result.json\n${sha256(summary)}  browser-summary.md\n`,
  );

  await page.close();
  await browser.close();
}

observe().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
