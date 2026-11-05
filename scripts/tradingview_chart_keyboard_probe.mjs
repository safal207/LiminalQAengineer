#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    args[key.slice(2)] = value;
  }
  return args;
}

async function settle(page, config, url) {
  let response = null;
  let error = null;
  try {
    response = await page.goto(url, {waitUntil: "domcontentloaded", timeout: config.navigation_timeout_ms});
  } catch (caught) {
    error = String(caught?.message || caught);
  }
  await sleep(config.settle_ms);
  return {status: response?.status() ?? null, error, final_url: page.url()};
}

async function inspectStatic(page) {
  return page.evaluate(() => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
    };
    const name = (element) => normalize(
      element.getAttribute("aria-label") ||
      element.getAttribute("title") ||
      element.getAttribute("alt") ||
      element.textContent,
    );
    const interactiveSelector = "a[href], button, input, select, textarea, [role='button'], [role='link'], [role='tab'], [role='menuitem'], [tabindex]";
    const interactives = [...document.querySelectorAll(interactiveSelector)].filter(visible).map((element) => ({
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role"),
      qa: element.getAttribute("data-qa-id"),
      name: name(element),
      tabindex_attribute: element.getAttribute("tabindex"),
      tab_index: element.tabIndex,
      disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true"),
      html: element.outerHTML.slice(0, 700),
    }));
    const enabled = interactives.filter((element) => !element.disabled);
    const sequential = enabled.filter((element) => element.tab_index >= 0);
    const unnamedEnabled = enabled.filter((element) => !element.name);
    const unnamedSequential = sequential.filter((element) => !element.name);
    const nested = [...document.querySelectorAll("button button, button a[href], a[href] button, [role='button'] button, button [role='button']")]
      .filter(visible)
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role"),
        name: name(element),
        parent_html: element.parentElement?.outerHTML.slice(0, 1000) || null,
      }));
    const body = normalize(document.body?.innerText || "");
    return {
      title: document.title,
      body_length: body.length,
      body_sha256_input: body,
      canvas_count: [...document.querySelectorAll("canvas")].filter(visible).length,
      svg_count: [...document.querySelectorAll("svg")].filter(visible).length,
      iframe_count: document.querySelectorAll("iframe").length,
      main_landmark_count: document.querySelectorAll("main, [role='main']").length,
      navigation_landmark_count: document.querySelectorAll("nav, [role='navigation']").length,
      interactive_count: interactives.length,
      enabled_interactive_count: enabled.length,
      sequential_focusable_count: sequential.length,
      unnamed_enabled_count: unnamedEnabled.length,
      unnamed_sequential_count: unnamedSequential.length,
      sequential_sample: sequential.slice(0, 100),
      unnamed_enabled_sample: unnamedEnabled.slice(0, 100),
      nested_interactive_count: nested.length,
      nested_interactive_sample: nested.slice(0, 50),
    };
  });
}

async function activeState(page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!element || element === document.body || element === document.documentElement) return null;
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role"),
      qa: element.getAttribute("data-qa-id"),
      name: normalize(element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent),
      tabindex_attribute: element.getAttribute("tabindex"),
      tab_index: element.tabIndex,
      rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      outline_style: style.outlineStyle,
      outline_width: style.outlineWidth,
      box_shadow: style.boxShadow,
    };
  });
}

async function tabTrace(page, steps) {
  const trace = [];
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press("Tab");
    await sleep(75);
    trace.push(await activeState(page));
  }
  return trace;
}

function summarizeTrace(trace) {
  const nonNull = trace.filter(Boolean);
  const unique = [...new Map(nonNull.map((item) => [`${item.tag}|${item.role || ""}|${item.qa || ""}|${item.name}`, item])).values()];
  return {
    steps: trace.length,
    non_null_steps: nonNull.length,
    unique_focus_targets: unique.length,
    first_focus: nonNull[0] || null,
    unique_targets: unique,
    trace,
  };
}

async function inspectFrames(page) {
  const output = [];
  for (const frame of page.frames()) {
    let state;
    try {
      state = await frame.evaluate(() => {
        const visible = (element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
        };
        const selector = "a[href], button, input, select, textarea, [role='button'], [role='link'], [role='tab'], [role='menuitem'], [tabindex]";
        const items = [...document.querySelectorAll(selector)].filter(visible);
        return {
          title: document.title,
          body_length: (document.body?.innerText || "").length,
          visible_interactive_count: items.length,
          sequential_focusable_count: items.filter((element) => !element.disabled && element.getAttribute("aria-disabled") !== "true" && element.tabIndex >= 0).length,
        };
      });
    } catch (error) {
      state = {error: String(error?.message || error)};
    }
    output.push({url: frame.url(), is_main_frame: frame === page.mainFrame(), ...state});
  }
  return output;
}

async function observeChart(browser, config, profile, outputDir) {
  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  const consoleEntries = [];
  page.on("console", (message) => {
    if (consoleEntries.length < 100) consoleEntries.push({type: message.type(), text: message.text().slice(0, 1000)});
  });

  const navigation = await settle(page, config, config.chart_url);
  const staticState = await inspectStatic(page);
  const body = staticState.body_sha256_input;
  delete staticState.body_sha256_input;
  staticState.body_sha256 = sha256(body);
  const frames = await inspectFrames(page);

  await page.evaluate(() => {
    document.activeElement?.blur?.();
    document.body?.focus?.();
  });
  const initialTrace = summarizeTrace(await tabTrace(page, config.tab_steps));
  await page.screenshot({path: path.join(outputDir, `${profile.id}-chart-after-tabs.png`), fullPage: true});

  const clickPoint = profile.id === "desktop"
    ? {x: Math.max(100, Math.floor(profile.viewport.width * 0.45)), y: Math.max(150, Math.floor(profile.viewport.height * 0.45))}
    : {x: Math.max(80, Math.floor(profile.viewport.width * 0.5)), y: Math.max(150, Math.floor(profile.viewport.height * 0.45))};
  await page.mouse.click(clickPoint.x, clickPoint.y);
  await sleep(500);
  const activeAfterClick = await activeState(page);
  const postClickTrace = summarizeTrace(await tabTrace(page, config.tab_steps));
  await page.screenshot({path: path.join(outputDir, `${profile.id}-chart-after-click-tabs.png`), fullPage: true});

  await page.close();
  return {
    profile: profile.id,
    navigation,
    static_state: staticState,
    frames,
    click_point: clickPoint,
    active_after_click: activeAfterClick,
    initial_tab_trace: initialTrace,
    post_click_tab_trace: postClickTrace,
    console: {
      error_count: consoleEntries.filter((entry) => entry.type === "error").length,
      entries: consoleEntries,
    },
  };
}

async function observeStatement(browser, config) {
  const page = await browser.newPage();
  const profile = config.profiles[0];
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  const navigation = await settle(page, config, config.accessibility_url);
  const evidence = await page.evaluate(() => {
    const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const lower = text.toLowerCase();
    const context = (needle) => {
      const index = lower.indexOf(needle.toLowerCase());
      return index < 0 ? null : text.slice(Math.max(0, index - 180), Math.min(text.length, index + 850));
    };
    return {
      chart_keyboard_context: context("This functionality covers the top bar"),
      focus_visibility_context: context("Focus visibility"),
      website_keyboard_context: context("All elements on our website are accessible via keyboard navigation"),
      body_sha256_input: text,
    };
  });
  const body = evidence.body_sha256_input;
  delete evidence.body_sha256_input;
  evidence.body_sha256 = sha256(body);
  await page.close();
  return {navigation, ...evidence};
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = args.config;
  const chromePath = args.chrome;
  const outputDir = args["output-dir"];
  if (!configPath || !chromePath || !outputDir) throw new Error("Required: --config --chrome --output-dir");
  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  await fs.rm(outputDir, {recursive: true, force: true});
  await fs.mkdir(outputDir, {recursive: true});

  const browser = await puppeteer.launch({executablePath: chromePath, headless: true, args: ["--no-sandbox", "--disable-dev-shm-usage"]});
  let statement;
  const profiles = [];
  try {
    statement = await observeStatement(browser, config);
    for (const profile of config.profiles) profiles.push(await observeChart(browser, config, profile, outputDir));
  } finally {
    await browser.close();
  }

  const loaded = profiles.every((entry) => entry.navigation.status === 200 && entry.static_state.canvas_count > 0);
  const noInitialFocus = profiles.every((entry) => entry.initial_tab_trace.unique_focus_targets === 0);
  const noPostClickFocus = profiles.every((entry) => entry.post_click_tab_trace.unique_focus_targets === 0);
  const enabledUnnamed = profiles.map((entry) => ({profile: entry.profile, count: entry.static_state.unnamed_enabled_count, sample: entry.static_state.unnamed_enabled_sample}));
  const nested = profiles.map((entry) => ({profile: entry.profile, count: entry.static_state.nested_interactive_count, sample: entry.static_state.nested_interactive_sample}));

  const result = {
    schema_version: "liminalqa-tradingview-chart-keyboard-result-v1",
    observed_at: new Date().toISOString(),
    center_of_coordinates: {
      O: "public BITSTAMP:BTCUSD chart + profile + viewport + unauthenticated state + observation time",
      N: "keyboard-only passive browser observer",
      T: "loaded chart -> 40 Tab presses -> neutral chart click -> 40 Tab presses",
    },
    statement,
    profiles,
    verdicts: {
      chart_loaded_in_both_profiles: loaded ? "CONFIRMED" : "NOT_CONFIRMED",
      initial_keyboard_navigation_contract: loaded && noInitialFocus ? "CONFIRMED_GAP" : "NOT_CONFIRMED",
      post_chart_activation_keyboard_navigation_contract: loaded && noPostClickFocus ? "CONFIRMED_GAP" : "NOT_CONFIRMED",
      enabled_controls_without_accessible_name: enabledUnnamed.some((entry) => entry.count > 0) ? "CONFIRMED_PUBLIC_SURFACE" : "NOT_OBSERVED",
      nested_interactive_controls: nested.some((entry) => entry.count > 0) ? "CONFIRMED_INVALID_INTERACTIVE_STRUCTURE" : "NOT_OBSERVED",
    },
    evidence_summary: {enabled_unnamed: enabledUnnamed, nested_interactive: nested},
    boundaries: config.boundaries,
    limitations: config.limitations,
    authority: {mode: "evidence_only", grants: {ownership: false, approval: false, execution: false, external_submission: false, delivery: false, deployment: false, merge: false}},
  };
  const text = `${JSON.stringify(result, null, 2)}\n`;
  await fs.writeFile(path.join(outputDir, "tradingview-chart-keyboard-result.json"), text);
  const summary = `# TradingView chart keyboard contract probe\n\nObserved: ${result.observed_at}\n\n## Verdicts\n\n${Object.entries(result.verdicts).map(([key, value]) => `- ${key}: **${value}**`).join("\n")}\n\n## Matrix\n\n${profiles.map((entry) => `- ${entry.profile}: canvas=${entry.static_state.canvas_count}; sequential DOM focusables=${entry.static_state.sequential_focusable_count}; initial unique focus=${entry.initial_tab_trace.unique_focus_targets}; post-click unique focus=${entry.post_click_tab_trace.unique_focus_targets}; enabled unnamed=${entry.static_state.unnamed_enabled_count}; nested interactive=${entry.static_state.nested_interactive_count}`).join("\n")}\n\n## Boundary\n\nPublic chart, keyboard presses, and one neutral chart click only. No login, account, form, publishing, trading, direct API, fuzzing, load testing, or server-state changes.\n`;
  await fs.writeFile(path.join(outputDir, "tradingview-chart-keyboard-summary.md"), summary);
  await fs.writeFile(path.join(outputDir, "SHA256SUMS.txt"), `${sha256(text)}  tradingview-chart-keyboard-result.json\n${sha256(summary)}  tradingview-chart-keyboard-summary.md\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
