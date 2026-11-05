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

function walkAccessibility(node, output = {nodes: 0, unnamed_interactive: 0, names: []}) {
  if (!node) return output;
  output.nodes += 1;
  const role = String(node.role || "").toLowerCase();
  const interactive = [
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
  ].includes(role);
  const name = normalizeText(node.name);
  if (interactive && !name) output.unnamed_interactive += 1;
  if (name && output.names.length < 250) output.names.push({role, name});
  for (const child of node.children || []) walkAccessibility(child, output);
  return output;
}

async function dismissConsent(page) {
  const labels = [
    "accept all",
    "accept",
    "allow all",
    "agree",
    "i agree",
    "принять все",
    "принять",
    "согласен",
  ];
  let clicked = 0;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const didClick = await page
      .evaluate((acceptedLabels) => {
        const candidates = [...document.querySelectorAll("button, [role='button']")];
        const target = candidates.find((element) => {
          const text = (element.textContent || element.getAttribute("aria-label") || "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return (
            acceptedLabels.includes(text) &&
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== "hidden" &&
            style.display !== "none"
          );
        });
        if (!target) return false;
        target.click();
        return true;
      }, labels)
      .catch(() => false);
    if (didClick) {
      clicked += 1;
      await sleep(800);
    } else {
      break;
    }
  }
  return clicked;
}

async function keyboardTrace(page, steps) {
  const trace = [];
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press("Tab");
    await sleep(75);
    const state = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const text = (element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160);
      const label = (
        element.getAttribute("aria-label") ||
        element.getAttribute("title") ||
        element.getAttribute("alt") ||
        text
      ).trim();
      return {
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role"),
        label,
        href: element instanceof HTMLAnchorElement ? element.href : null,
        rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
        visible: rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none",
        outline_style: style.outlineStyle,
        outline_width: style.outlineWidth,
        box_shadow: style.boxShadow,
      };
    });
    trace.push(state);
  }
  return trace;
}

async function inspectDom(page, target) {
  return page.evaluate((targetKind) => {
    const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0
      );
    };
    const accessibleName = (element) =>
      normalize(
        element.getAttribute("aria-label") ||
          element.getAttribute("aria-labelledby") ||
          element.getAttribute("title") ||
          element.getAttribute("alt") ||
          element.textContent,
      );

    const bodyText = normalize(document.body?.innerText || "");
    const lower = bodyText.toLowerCase();
    const buttons = [...document.querySelectorAll("button, [role='button']")].filter(visible);
    const links = [...document.querySelectorAll("a[href]")].filter(visible);
    const images = [...document.querySelectorAll("img")].filter(visible);
    const inputs = [...document.querySelectorAll("input, textarea, select")].filter(visible);
    const ids = [...document.querySelectorAll("[id]")].map((element) => element.id).filter(Boolean);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    const skipElements = [...document.querySelectorAll("a, button, [role='button']")]
      .filter((element) => /skip( to)? (main|content)/i.test(accessibleName(element)))
      .map((element) => ({
        name: accessibleName(element),
        visible: visible(element),
        href: element instanceof HTMLAnchorElement ? element.href : null,
      }));

    const canvas = [...document.querySelectorAll("canvas")].filter(visible);
    const svg = [...document.querySelectorAll("svg")].filter(visible);
    const videos = [...document.querySelectorAll("video")].filter(visible);
    const pauseButtons = buttons.filter((element) => /pause|stop animation/i.test(accessibleName(element)));
    const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
      .filter(visible)
      .map((element) => ({level: Number(element.tagName.slice(1)), text: normalize(element.textContent).slice(0, 250)}));

    const repeatedAlt = {};
    for (const image of images) {
      const alt = normalize(image.getAttribute("alt"));
      if (alt) repeatedAlt[alt] = (repeatedAlt[alt] || 0) + 1;
    }

    const stateVocabulary = [
      "market closed",
      "no trades",
      "delayed",
      "offline",
      "reconnecting",
      "connection lost",
      "data is delayed",
      "real-time",
      "real time",
    ];
    const stateTerms = stateVocabulary.filter((term) => lower.includes(term));
    const antiBotTerms = [
      "verify you are human",
      "checking your browser",
      "captcha",
      "access denied",
      "unusual traffic",
      "temporarily blocked",
    ].filter((term) => lower.includes(term));

    const currentPriceMatch = bodyText.match(/current price[^.]{0,180}/i);
    const volumeMatch = bodyText.match(/trading volume[^.]{0,180}/i);
    const twentyFourHourMatch = bodyText.match(/(?:24h|24 hours)[^.]{0,180}/i);
    const btcContexts = [];
    const regex = /BTCUSD|Bitcoin|BTC\/USD/gi;
    let match;
    while ((match = regex.exec(bodyText)) && btcContexts.length < 12) {
      btcContexts.push(bodyText.slice(Math.max(0, match.index - 80), Math.min(bodyText.length, match.index + 260)));
    }

    const unnamedButtons = buttons
      .filter((element) => !accessibleName(element))
      .slice(0, 100)
      .map((element) => ({html: element.outerHTML.slice(0, 500)}));
    const unnamedLinks = links
      .filter((element) => !accessibleName(element))
      .slice(0, 100)
      .map((element) => ({href: element.href, html: element.outerHTML.slice(0, 500)}));
    const unlabeledInputs = inputs
      .filter((element) => {
        const id = element.id;
        const explicitLabel = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
        return !accessibleName(element) && !explicitLabel;
      })
      .slice(0, 100)
      .map((element) => ({type: element.getAttribute("type"), name: element.getAttribute("name")}));

    const resourceHints = [...document.querySelectorAll("link[rel='preload'], link[rel='modulepreload'], link[rel='prefetch']")].map(
      (element) => ({rel: element.rel, href: element.href, as: element.getAttribute("as")}));

    return {
      target_kind: targetKind,
      title: document.title,
      html_lang: document.documentElement.lang,
      body_text: bodyText,
      body_text_sha256_input: bodyText,
      body_length: bodyText.length,
      anti_bot_terms: antiBotTerms,
      state_terms: stateTerms,
      market_closed_count: (lower.match(/market closed/g) || []).length,
      no_trades_count: (lower.match(/no trades/g) || []).length,
      current_price_context: currentPriceMatch?.[0] || null,
      volume_context: volumeMatch?.[0] || null,
      twenty_four_hour_context: twentyFourHourMatch?.[0] || null,
      btc_contexts: btcContexts,
      visible_canvas_count: canvas.length,
      visible_svg_count: svg.length,
      visible_video_count: videos.length,
      visible_pause_button_count: pauseButtons.length,
      visible_button_count: buttons.length,
      unnamed_visible_buttons: unnamedButtons,
      visible_link_count: links.length,
      unnamed_visible_links: unnamedLinks,
      visible_image_count: images.length,
      missing_alt_visible_images: images.filter((image) => !normalize(image.getAttribute("alt"))).length,
      repeated_image_alt: Object.entries(repeatedAlt)
        .filter(([, count]) => count > 1)
        .sort((left, right) => right[1] - left[1])
        .slice(0, 30),
      visible_input_count: inputs.length,
      unlabeled_visible_inputs: unlabeledInputs,
      duplicate_ids: duplicateIds.slice(0, 100),
      headings,
      main_landmark_count: document.querySelectorAll("main, [role='main']").length,
      navigation_landmark_count: document.querySelectorAll("nav, [role='navigation']").length,
      skip_elements: skipElements,
      resource_hints: resourceHints.slice(0, 200),
    };
  }, target.kind);
}

async function observeTarget(browser, config, profile, target, outputDir) {
  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);

  const consoleEntries = [];
  const failedRequests = [];
  const responseStats = [];
  page.on("console", (message) => {
    if (consoleEntries.length >= config.max_console_entries) return;
    consoleEntries.push({type: message.type(), text: message.text().slice(0, 1000)});
  });
  page.on("requestfailed", (request) => {
    if (failedRequests.length >= config.max_failed_requests) return;
    failedRequests.push({url: request.url(), method: request.method(), error: request.failure()?.errorText || null});
  });
  page.on("response", (response) => {
    if (responseStats.length >= 2000) return;
    const request = response.request();
    responseStats.push({url: response.url(), status: response.status(), resource_type: request.resourceType()});
  });

  const startedAt = Date.now();
  let navigationResponse = null;
  let navigationError = null;
  try {
    navigationResponse = await page.goto(target.url, {waitUntil: "domcontentloaded", timeout: config.navigation_timeout_ms});
  } catch (error) {
    navigationError = String(error?.message || error);
  }
  const consentClicks = await dismissConsent(page).catch(() => 0);
  await sleep(config.settle_ms);
  const settledAt = Date.now();

  const dom = await inspectDom(page, target);
  const bodyText = dom.body_text_sha256_input;
  delete dom.body_text_sha256_input;
  dom.body_text_sha256 = sha256(bodyText);
  dom.body_text_sample = bodyText.slice(0, config.max_body_sample_chars);
  delete dom.body_text;

  const accessibilityTree = await page.accessibility.snapshot({interestingOnly: false}).catch(() => null);
  const accessibility = walkAccessibility(accessibilityTree);
  const keyboard = await keyboardTrace(page, config.keyboard_tab_steps).catch(() => []);
  const uniqueFocus = new Set(
    keyboard
      .filter(Boolean)
      .map((item) => `${item.tag}|${item.role || ""}|${item.label}|${item.href || ""}`),
  );

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
              dom_content_loaded_ms: navigation.domContentLoadedEventEnd,
              load_event_ms: navigation.loadEventEnd,
              response_start_ms: navigation.responseStart,
              response_end_ms: navigation.responseEnd,
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

  const screenshotPath = path.join(outputDir, `${profile.id}-${target.id}.png`);
  await page.screenshot({path: screenshotPath, fullPage: true}).catch(() => null);

  const firstFocus = keyboard.find(Boolean) || null;
  const result = {
    profile: profile.id,
    target_id: target.id,
    target_kind: target.kind,
    requested_url: target.url,
    final_url: page.url(),
    navigation_status: navigationResponse?.status() ?? null,
    navigation_error: navigationError,
    started_at: new Date(startedAt).toISOString(),
    settled_at: new Date(settledAt).toISOString(),
    wall_time_ms: settledAt - startedAt,
    consent_clicks: consentClicks,
    dom,
    accessibility: {
      node_count: accessibility.nodes,
      unnamed_interactive_count: accessibility.unnamed_interactive,
      named_node_sample: accessibility.names.slice(0, 100),
    },
    keyboard: {
      attempted_steps: config.keyboard_tab_steps,
      unique_focus_targets: uniqueFocus.size,
      first_focus: firstFocus,
      trace: keyboard,
      skip_link_reached: keyboard.some((item) => item && /skip( to)? (main|content)/i.test(item.label || "")),
    },
    network: {
      response_count: responseStats.length,
      status_4xx_count: responseStats.filter((entry) => entry.status >= 400 && entry.status < 500).length,
      status_5xx_count: responseStats.filter((entry) => entry.status >= 500).length,
      failed_requests: failedRequests,
      failed_request_count: failedRequests.length,
      response_sample: responseStats.slice(0, 300),
    },
    console: {
      entries: consoleEntries,
      error_count: consoleEntries.filter((entry) => entry.type === "error").length,
      warning_count: consoleEntries.filter((entry) => entry.type === "warning").length,
    },
    performance,
    screenshot: path.basename(screenshotPath),
  };

  await page.close();
  return result;
}

function aggregate(results, config) {
  const byTarget = Object.fromEntries(
    config.targets.map((target) => [target.id, results.filter((result) => result.target_id === target.id)]),
  );
  const symbol = byTarget["btc-symbol"] || [];
  const chart = byTarget["btc-chart"] || [];
  const accessibilityPages = byTarget.accessibility || [];

  const marketContradiction =
    symbol.length === config.profiles.length &&
    symbol.every(
      (entry) =>
        entry.dom.market_closed_count > 0 &&
        entry.dom.no_trades_count > 0 &&
        Boolean(entry.dom.current_price_context) &&
        Boolean(entry.dom.volume_context || entry.dom.twenty_four_hour_context),
    );

  const chartLoaded = chart.map((entry) => ({
    profile: entry.profile,
    visible_canvas_count: entry.dom.visible_canvas_count,
    visible_svg_count: entry.dom.visible_svg_count,
    anti_bot: entry.dom.anti_bot_terms.length > 0,
    navigation_status: entry.navigation_status,
  }));

  const accessibleNameDebt = results
    .filter((entry) => entry.dom.anti_bot_terms.length === 0)
    .map((entry) => ({
      profile: entry.profile,
      target_id: entry.target_id,
      unnamed_dom_buttons: entry.dom.unnamed_visible_buttons.length,
      unnamed_dom_links: entry.dom.unnamed_visible_links.length,
      unnamed_ax_interactive: entry.accessibility.unnamed_interactive_count,
    }));

  const skipLinkObserved = results.map((entry) => ({
    profile: entry.profile,
    target_id: entry.target_id,
    dom_skip_elements: entry.dom.skip_elements,
    keyboard_skip_link_reached: entry.keyboard.skip_link_reached,
    first_focus: entry.keyboard.first_focus,
  }));

  const mobileDesktopDivergence = config.targets.map((target) => {
    const entries = byTarget[target.id] || [];
    const desktop = entries.find((entry) => entry.profile === "desktop");
    const mobile = entries.find((entry) => entry.profile === "mobile");
    return {
      target_id: target.id,
      status_differs: desktop?.navigation_status !== mobile?.navigation_status,
      final_url_differs: desktop?.final_url !== mobile?.final_url,
      anti_bot_differs:
        Boolean(desktop?.dom.anti_bot_terms.length) !== Boolean(mobile?.dom.anti_bot_terms.length),
      canvas_count_delta:
        (mobile?.dom.visible_canvas_count ?? 0) - (desktop?.dom.visible_canvas_count ?? 0),
      body_length_ratio:
        desktop?.dom.body_length && mobile?.dom.body_length
          ? mobile.dom.body_length / desktop.dom.body_length
          : null,
    };
  });

  const antiBotCount = results.filter((entry) => entry.dom.anti_bot_terms.length > 0).length;
  const allNavigationsReturned = results.every((entry) => entry.navigation_status !== null);
  const largeConsoleErrors = results
    .filter((entry) => entry.console.error_count >= 5)
    .map((entry) => ({profile: entry.profile, target_id: entry.target_id, error_count: entry.console.error_count}));

  const accessibilityStatementRuntimeGap =
    accessibilityPages.length === config.profiles.length &&
    results.filter((entry) => entry.target_id !== "accessibility").every(
      (entry) => entry.dom.skip_elements.length === 0 && entry.keyboard.skip_link_reached === false,
    );

  return {
    observed_route_profile_count: results.length,
    navigation_coverage: {
      all_returned_http_response: allNavigationsReturned,
      anti_bot_variant_count: antiBotCount,
    },
    verdicts: {
      btc_symbol_market_state_consistency: marketContradiction
        ? "CONFIRMED_CONTRADICTORY_PUBLIC_STATE"
        : "NOT_CONFIRMED",
      chart_surface_loading: chart.every(
        (entry) => entry.dom.visible_canvas_count > 0 || entry.dom.visible_svg_count > 0 || entry.dom.anti_bot_terms.length > 0,
      )
        ? "OBSERVED_OR_ENVIRONMENT_BLOCKED"
        : "NEEDS_EVIDENCE",
      accessibility_skip_content_contract: accessibilityStatementRuntimeGap
        ? "CONFIRMED_DOCUMENTATION_RUNTIME_GAP_CANDIDATE"
        : "NOT_CONFIRMED",
      accessible_name_debt: accessibleNameDebt.some(
        (entry) => entry.unnamed_dom_buttons > 0 || entry.unnamed_dom_links > 0 || entry.unnamed_ax_interactive > 0,
      )
        ? "CONFIRMED_PUBLIC_SURFACE"
        : "NOT_OBSERVED",
      mobile_desktop_route_divergence: mobileDesktopDivergence.some(
        (entry) => entry.status_differs || entry.final_url_differs || entry.anti_bot_differs,
      )
        ? "NEEDS_REVIEW"
        : "NOT_OBSERVED",
      high_console_error_routes: largeConsoleErrors.length > 0 ? "NEEDS_REVIEW" : "NOT_OBSERVED",
    },
    btc_symbol_evidence: symbol.map((entry) => ({
      profile: entry.profile,
      status: entry.navigation_status,
      final_url: entry.final_url,
      market_closed_count: entry.dom.market_closed_count,
      no_trades_count: entry.dom.no_trades_count,
      current_price_context: entry.dom.current_price_context,
      volume_context: entry.dom.volume_context,
      twenty_four_hour_context: entry.dom.twenty_four_hour_context,
      body_text_sha256: entry.dom.body_text_sha256,
      screenshot: entry.screenshot,
    })),
    chart_loading: chartLoaded,
    accessible_name_debt: accessibleNameDebt,
    skip_link_observation: skipLinkObserved,
    mobile_desktop_divergence: mobileDesktopDivergence,
    high_console_error_routes: largeConsoleErrors,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = args.config;
  const chromePath = args.chrome;
  const outputDir = args["output-dir"];
  if (!configPath || !chromePath || !outputDir) {
    throw new Error("Required: --config --chrome --output-dir");
  }

  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  await fs.rm(outputDir, {recursive: true, force: true});
  await fs.mkdir(outputDir, {recursive: true});

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });

  const results = [];
  try {
    for (const profile of config.profiles) {
      for (const target of config.targets) {
        const result = await observeTarget(browser, config, profile, target, outputDir);
        results.push(result);
      }
    }
  } finally {
    await browser.close();
  }

  const aggregateResult = aggregate(results, config);
  const result = {
    schema_version: "liminalqa-tradingview-public-surface-result-v1",
    observed_at: new Date().toISOString(),
    center_of_coordinates: {
      O: "public URL + browser profile + viewport + unauthenticated state + observation time",
      N: "passive unauthenticated browser observer",
      axes: {
        X: "domain -> route -> component -> visible financial/community state",
        Y: "loading -> rendered -> accessible -> current/delayed/closed/error state",
        Z: "desktop/mobile user-agent and viewport",
        T: "navigation -> DOM ready -> settled page -> keyboard traversal",
      },
    },
    config_sha256: sha256(JSON.stringify(config)),
    aggregate: aggregateResult,
    observations: results,
    boundaries: config.boundaries,
    limitations: config.limitations,
    authority: {
      mode: "evidence_only",
      grants: {
        ownership: false,
        approval: false,
        execution: false,
        external_submission: false,
        delivery: false,
        deployment: false,
        merge: false,
      },
    },
  };

  const resultText = `${JSON.stringify(result, null, 2)}\n`;
  await fs.writeFile(path.join(outputDir, "tradingview-public-surface-result.json"), resultText);

  const rows = results
    .map(
      (entry) =>
        `| ${entry.profile} | ${entry.target_id} | ${entry.navigation_status ?? "n/a"} | ${entry.dom.visible_canvas_count} | ${entry.dom.unnamed_visible_buttons.length} | ${entry.accessibility.unnamed_interactive_count} | ${entry.keyboard.unique_focus_targets} | ${entry.console.error_count} | ${entry.dom.anti_bot_terms.join(", ") || "—"} |`,
    )
    .join("\n");

  const summary = `# TradingView public unauthenticated audit\n\n` +
    `Observed: ${result.observed_at}\n\n` +
    `## Verdicts\n\n` +
    Object.entries(aggregateResult.verdicts)
      .map(([key, value]) => `- ${key}: **${value}**`)
      .join("\n") +
    `\n\n## Coordinate model\n\n` +
    `O = public URL + profile + viewport + no-auth state + time. N = passive browser.\n\n` +
    `## Matrix\n\n` +
    `| Profile | Target | HTTP | Canvas | Unnamed DOM buttons | Unnamed AX controls | Unique Tab targets | Console errors | Environment block |\n` +
    `|---|---|---:|---:|---:|---:|---:|---:|---|\n${rows}\n\n` +
    `## BTCUSD state consistency\n\n` +
    `${JSON.stringify(aggregateResult.btc_symbol_evidence, null, 2)}\n\n` +
    `## Safety\n\n` +
    `Public pages, natural navigation and keyboard focus only. No login, accounts, direct APIs, forms, publishing, trading, fuzzing, load testing, or server-state change.\n`;
  await fs.writeFile(path.join(outputDir, "tradingview-public-surface-summary.md"), summary);
  await fs.writeFile(
    path.join(outputDir, "SHA256SUMS.txt"),
    `${sha256(resultText)}  tradingview-public-surface-result.json\n${sha256(summary)}  tradingview-public-surface-summary.md\n`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
