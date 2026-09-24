#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");
const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key}`);
    result[key.slice(2)] = value;
  }
  return result;
}

async function loadJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

function originOf(rawUrl) {
  const url = new URL(rawUrl);
  return `${url.protocol}//${url.hostname}`;
}

function sanitizeUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch {
    return String(rawUrl || "").slice(0, 500);
  }
}

function validate(config, contract) {
  if (config.schema_version !== "liminalqa-chatapp-public-rendered-v1") throw new Error("Unsupported rendered schema");
  if (contract.schema_version !== "liminalqa-chatapp-public-audit-v1") throw new Error("Unsupported contract schema");
  if (contract.target?.canonical_origin !== "https://chatapp.online") throw new Error("ChatApp origin must be exact");
  const profileIds = (config.profiles || []).map((item) => item.id).sort();
  if (profileIds.join(",") !== "desktop,mobile") throw new Error("Exactly desktop and mobile profiles are required");
  const allowed = new Set(contract.allowed_paths || []);
  for (const target of contract.targets || []) {
    const url = new URL(target.url);
    if (originOf(target.url) !== contract.target.canonical_origin || url.search || url.hash || !allowed.has(url.pathname || "/")) {
      throw new Error(`Target outside bounded contract: ${target.url}`);
    }
  }
  const boundaries = config.boundaries || {};
  for (const key of ["public_pages_only", "natural_navigation_only", "passive_browser_observation", "keyboard_navigation_only"]) {
    if (boundaries[key] !== true) throw new Error(`${key} must be true`);
  }
  for (const key of [
    "authentication", "account_access", "form_submission", "button_clicks", "direct_api_testing",
    "email_or_external_contact", "enumeration", "fuzzing", "load_testing", "active_security_testing",
    "server_state_change", "external_submission_authorized", "deployment_authorized", "merge_authorized",
  ]) {
    if (boundaries[key] !== false) throw new Error(`${key} must be false`);
  }
}

function markerContext(haystack, marker, radius = 170) {
  const index = haystack.toLocaleLowerCase().indexOf(marker.toLocaleLowerCase());
  if (index < 0) return null;
  return haystack.slice(Math.max(0, index - radius), Math.min(haystack.length, index + marker.length + radius));
}

function evaluateAssertion(assertion, visibleText, visibleLinks) {
  const linksText = visibleLinks.map((link) => `${link.text} ${link.href}`).join(" ");
  const combined = `${visibleText} ${linksText}`;
  const source = assertion.case_sensitive ? combined : combined.toLocaleLowerCase();
  if (assertion.type === "all_of" || assertion.type === "any_of") {
    const markers = assertion.markers.map((marker) => {
      const needle = assertion.case_sensitive ? marker : marker.toLocaleLowerCase();
      return {marker, present: source.includes(needle), context: markerContext(combined, marker)};
    });
    return {
      id: assertion.id,
      type: assertion.type,
      passed: assertion.type === "all_of" ? markers.every((item) => item.present) : markers.some((item) => item.present),
      markers,
    };
  }
  if (assertion.type === "occurrence") {
    const marker = assertion.marker;
    const needle = assertion.case_sensitive ? marker : marker.toLocaleLowerCase();
    let count = 0;
    let from = 0;
    while (true) {
      const index = source.indexOf(needle, from);
      if (index < 0) break;
      count += 1;
      from = index + needle.length;
    }
    return {
      id: assertion.id,
      type: assertion.type,
      marker,
      observed_occurrences: count,
      min_occurrences: assertion.min_occurrences,
      passed: count >= assertion.min_occurrences,
      context: markerContext(combined, marker),
    };
  }
  throw new Error(`Unsupported assertion type: ${assertion.type}`);
}

async function inspectDom(page, config) {
  return page.evaluate((limits) => {
    const normalizeText = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
    };
    const nameOf = (element) => normalizeText(
      element.getAttribute("aria-label") || element.getAttribute("title") || element.getAttribute("alt") || element.textContent,
    );
    const bodyText = normalizeText(document.body?.innerText || "");
    const links = [...document.querySelectorAll("a[href]")]
      .filter(visible)
      .slice(0, limits.maxVisibleLinks)
      .map((element) => ({
        text: nameOf(element).slice(0, 250),
        href: element.href.split(/[?#]/)[0],
        internal: element.hostname === location.hostname,
      }));
    const buttons = [...document.querySelectorAll("button,[role='button']")].filter(visible);
    const inputs = [...document.querySelectorAll("input,textarea,select")].filter(visible);
    const images = [...document.querySelectorAll("img")].filter(visible);
    const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")]
      .filter(visible)
      .map((element) => ({level: Number(element.tagName.slice(1)), text: normalizeText(element.textContent).slice(0, 300)}));
    const lower = bodyText.toLowerCase();
    const antiBotTerms = ["verify you are human", "checking your browser", "captcha", "access denied", "unusual traffic", "temporarily blocked"]
      .filter((term) => lower.includes(term));
    return {
      title: document.title,
      html_lang: document.documentElement.lang,
      visible_text: bodyText,
      visible_text_length: bodyText.length,
      visible_links: links,
      visible_link_count: links.length,
      visible_button_count: buttons.length,
      visible_form_count: [...document.querySelectorAll("form")].filter(visible).length,
      visible_input_count: inputs.length,
      visible_image_count: images.length,
      missing_alt_visible_image_count: images.filter((image) => !normalizeText(image.getAttribute("alt"))).length,
      unlabeled_visible_input_count: inputs.filter((element) => {
        const explicit = element.id ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`) : null;
        return !nameOf(element) && !explicit;
      }).length,
      headings,
      h1_count: headings.filter((heading) => heading.level === 1).length,
      main_landmark_count: document.querySelectorAll("main,[role='main']").length,
      navigation_landmark_count: document.querySelectorAll("nav,[role='navigation']").length,
      anti_bot_terms: antiBotTerms,
    };
  }, {maxVisibleLinks: config.max_visible_links});
}

async function keyboardTrace(page, steps) {
  const trace = [];
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press("Tab");
    await sleep(50);
    trace.push(await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const label = (element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent || "")
        .replace(/\s+/g, " ").trim().slice(0, 180);
      return {
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role"),
        label,
        href: element instanceof HTMLAnchorElement ? element.href.split(/[?#]/)[0] : null,
        visible: rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden",
        outline_style: style.outlineStyle,
        outline_width: style.outlineWidth,
        box_shadow: style.boxShadow,
      };
    }));
  }
  return trace;
}

async function observeTarget(browser, config, contract, profile, target, outputDir) {
  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);

  const consoleEntries = [];
  const failedRequests = [];
  const responses = [];
  page.on("console", (message) => {
    if (consoleEntries.length < config.max_console_entries) consoleEntries.push({type: message.type(), text: message.text().slice(0, 1000)});
  });
  page.on("requestfailed", (request) => {
    if (failedRequests.length < config.max_failed_requests) failedRequests.push({
      url: sanitizeUrl(request.url()), method: request.method(), resource_type: request.resourceType(), error: request.failure()?.errorText || null,
    });
  });
  page.on("response", (response) => {
    if (responses.length < config.max_response_entries) responses.push({
      url: sanitizeUrl(response.url()), status: response.status(), resource_type: response.request().resourceType(),
    });
  });

  const startedAt = Date.now();
  let navigationResponse = null;
  let navigationError = null;
  try {
    navigationResponse = await page.goto(target.url, {waitUntil: "domcontentloaded", timeout: config.navigation_timeout_ms});
  } catch (error) {
    navigationError = String(error?.message || error);
  }
  await sleep(config.settle_ms);
  const finalUrl = page.url();
  const dom = await inspectDom(page, config);
  const visibleText = dom.visible_text;
  const assertions = target.assertions.map((assertion) => evaluateAssertion(assertion, visibleText, dom.visible_links));
  dom.visible_text_sha256 = sha256(visibleText);
  dom.visible_text_sample = visibleText.slice(0, config.max_body_sample_chars);
  delete dom.visible_text;

  const keyboard = await keyboardTrace(page, config.keyboard_tab_steps).catch(() => []);
  const uniqueFocusTargets = new Set(keyboard.filter(Boolean).map((item) => `${item.tag}|${item.role || ""}|${item.label}|${item.href || ""}`));
  const screenshot = `${profile.id}-${target.slug}.png`;
  const screenshotPath = path.join(outputDir, screenshot);
  await page.screenshot({path: screenshotPath, fullPage: true});
  const screenshotBytes = await fs.readFile(screenshotPath);
  const settledAt = Date.now();

  const result = {
    profile: profile.id,
    target_slug: target.slug,
    role: target.role,
    requested_url: target.url,
    final_url: sanitizeUrl(finalUrl),
    origin_stayed_bounded: originOf(finalUrl) === contract.target.canonical_origin,
    navigation_status: navigationResponse?.status() ?? null,
    navigation_error: navigationError,
    started_at: new Date(startedAt).toISOString(),
    settled_at: new Date(settledAt).toISOString(),
    wall_time_ms: settledAt - startedAt,
    assertions,
    all_assertions_passed: assertions.every((assertion) => assertion.passed),
    dom,
    keyboard: {attempted_steps: config.keyboard_tab_steps, unique_focus_targets: uniqueFocusTargets.size, trace: keyboard},
    network: {
      response_count: responses.length,
      status_4xx_count: responses.filter((entry) => entry.status >= 400 && entry.status < 500).length,
      status_5xx_count: responses.filter((entry) => entry.status >= 500).length,
      failed_request_count: failedRequests.length,
      failed_requests: failedRequests,
      response_sample: responses,
    },
    console: {
      error_count: consoleEntries.filter((entry) => entry.type === "error").length,
      warning_count: consoleEntries.filter((entry) => entry.type === "warning").length,
      entries: consoleEntries,
    },
    screenshot,
    screenshot_sha256: sha256(screenshotBytes),
  };
  await page.close();
  return result;
}

function aggregate(config, contract, observations) {
  const profileIds = config.profiles.map((profile) => profile.id);
  const index = new Map();
  for (const observation of observations) {
    const healthy = observation.origin_stayed_bounded
      && observation.navigation_status !== null
      && observation.navigation_status >= 200
      && observation.navigation_status < 400
      && observation.dom.anti_bot_terms.length === 0;
    for (const assertion of observation.assertions) {
      index.set(`${observation.profile}:${observation.target_slug}:${assertion.id}`, healthy && assertion.passed);
    }
  }

  const findings = contract.findings.map((finding) => {
    const profileEvidence = profileIds.map((profile) => {
      const refs = finding.evidence_refs.map((ref) => {
        const [targetSlug, assertionId] = ref.split(":");
        return {ref, passed: index.get(`${profile}:${targetSlug}:${assertionId}`) === true};
      });
      return {profile, refs, passed: refs.every((entry) => entry.passed)};
    });
    const acrossProfiles = profileEvidence.every((entry) => entry.passed);
    const anyProfile = profileEvidence.some((entry) => entry.passed);
    return {
      id: finding.id,
      title: finding.title,
      severity: finding.severity,
      state: acrossProfiles ? "CONFIRMED_PRODUCT_DEFECT_CANDIDATE" : anyProfile ? "PRODUCT_SIGNAL" : "NEEDS_EVIDENCE",
      rendered_reproduction_across_profiles: acrossProfiles,
      profile_evidence: profileEvidence,
      quality_lens: finding.quality_lens,
      system_lens: finding.system_lens,
      business_lens: finding.business_lens,
      root_cause_status: "HYPOTHESIS_ONLY",
      business_impact_status: "PLAUSIBLE_NOT_MEASURED",
    };
  });

  const expected = contract.targets.length * config.profiles.length;
  const complete = observations.length === expected;
  const bounded = observations.every((observation) => observation.origin_stayed_bounded);
  const candidates = findings.filter((finding) => finding.state === "CONFIRMED_PRODUCT_DEFECT_CANDIDATE").length;
  return {
    expected_observation_count: expected,
    observed_route_profile_count: observations.length,
    complete,
    all_final_origins_bounded: bounded,
    candidate_count: candidates,
    decision: !complete || !bounded ? "NEEDS_EVIDENCE" : candidates ? "RENDERED_PRODUCT_DEFECT_CANDIDATES" : "NO_RENDERED_CANDIDATE_CONFIRMED",
    findings,
    accessibility_summary: observations.map((observation) => ({
      profile: observation.profile,
      target_slug: observation.target_slug,
      missing_alt_visible_image_count: observation.dom.missing_alt_visible_image_count,
      unlabeled_visible_input_count: observation.dom.unlabeled_visible_input_count,
      h1_count: observation.dom.h1_count,
      main_landmark_count: observation.dom.main_landmark_count,
      unique_focus_targets: observation.keyboard.unique_focus_targets,
    })),
    runtime_signal_summary: observations.map((observation) => ({
      profile: observation.profile,
      target_slug: observation.target_slug,
      status: observation.navigation_status,
      console_errors: observation.console.error_count,
      network_4xx: observation.network.status_4xx_count,
      network_5xx: observation.network.status_5xx_count,
      failed_requests: observation.network.failed_request_count,
      anti_bot_terms: observation.dom.anti_bot_terms,
    })),
  };
}

function renderSummary(packet) {
  const lines = [
    "# LiminalQA · ChatApp rendered audit v0.2",
    "",
    `**Decision:** \`${packet.aggregate.decision}\`  `,
    `**Coverage:** \`${packet.aggregate.observed_route_profile_count}/${packet.aggregate.expected_observation_count}\`  `,
    `**Rendered candidates:** \`${packet.aggregate.candidate_count}/${packet.aggregate.findings.length}\`  `,
    `**Source head:** \`${packet.execution.source_head_sha}\``,
    "",
    "## Finding matrix",
    "",
    "| ID | Severity | State | Finding |",
    "|---|---|---|---|",
  ];
  for (const finding of packet.aggregate.findings) lines.push(`| ${finding.id} | ${finding.severity} | ${finding.state} | ${finding.title} |`);
  lines.push(
    "", "## Judgment boundary", "",
    "> Desktop/mobile reproduction can promote a public claim to a product-defect candidate.",
    "> It does not prove internal root cause, legal impact, conversion loss, or revenue loss.",
    "",
    "> No control activation, form submission, direct API testing, security testing, external contact, deployment, or merge is authorized.",
    "",
  );
  return lines.join("\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.config || !args.contract || !args.chrome || !args["output-dir"]) {
    throw new Error("Required: --config --contract --chrome --output-dir");
  }
  const [config, contract] = await Promise.all([loadJson(args.config), loadJson(args.contract)]);
  validate(config, contract);
  const outputDir = args["output-dir"];
  await fs.mkdir(outputDir, {recursive: true});
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });
  const observations = [];
  try {
    for (const target of contract.targets) {
      for (const profile of config.profiles) observations.push(await observeTarget(browser, config, contract, profile, target, outputDir));
    }
  } finally {
    await browser.close();
  }
  const packet = {
    schema_version: "liminalqa-chatapp-public-rendered-result-v1",
    audit_id: contract.audit_id,
    generated_at: new Date().toISOString(),
    execution: {
      run_id: process.env.GITHUB_RUN_ID || null,
      run_attempt: process.env.GITHUB_RUN_ATTEMPT || null,
      source_head_sha: process.env.GITHUB_HEAD_SHA || process.env.GITHUB_SHA || "local",
      workflow_sha: process.env.GITHUB_SHA || "local",
      base_sha: process.env.GITHUB_BASE_SHA || null,
      config_sha256: sha256(await fs.readFile(args.config)),
      contract_sha256: sha256(await fs.readFile(args.contract)),
      browser: "chromium_via_puppeteer_core",
    },
    coordinate_model: contract.coordinate_model,
    observations,
    aggregate: aggregate(config, contract, observations),
    limitations: config.limitations,
    authority: {
      mode: "evidence_only",
      grants: {ownership: false, approval: false, execution: false, external_submission: false, delivery: false, deployment: false, merge: false},
    },
  };
  await fs.writeFile(path.join(outputDir, "chatapp-rendered-result.json"), `${JSON.stringify(packet, null, 2)}\n`, "utf8");
  const summary = renderSummary(packet);
  await fs.writeFile(path.join(outputDir, "chatapp-rendered-summary.md"), summary, "utf8");
  console.log(summary);
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
