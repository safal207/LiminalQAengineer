#!/usr/bin/env node
/** Bounded Chromium probe for the Monetka public audit. No clicks or mutations. */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer-core';

const RESULT_SCHEMA = 'liminalqa-monetka-public-rendered-result-v1';

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith('--')) throw new Error(`Unexpected argument: ${arg}`);
    const key = arg.slice(2);
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) throw new Error(`Missing value for --${key}`);
    out[key] = value;
    i += 1;
  }
  for (const key of ['config', 'contract', 'chrome', 'output-dir']) {
    if (!out[key]) throw new Error(`Missing --${key}`);
  }
  return out;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function normalizeText(value) {
  return value.replace(/\s+/gu, ' ').trim();
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function origin(value) {
  return new URL(value).origin;
}

function markerContext(text, marker, radius = 180) {
  const index = text.toLocaleLowerCase('ru-RU').indexOf(marker.toLocaleLowerCase('ru-RU'));
  if (index < 0) return null;
  return text.slice(Math.max(0, index - radius), Math.min(text.length, index + marker.length + radius));
}

function evaluateAssertion(assertion, text) {
  const caseSensitive = Boolean(assertion.case_sensitive);
  const corpus = caseSensitive ? text : text.toLocaleLowerCase('ru-RU');
  if (['all_of', 'any_of', 'none_of'].includes(assertion.type)) {
    const markers = assertion.markers.map((marker) => {
      const needle = caseSensitive ? marker : marker.toLocaleLowerCase('ru-RU');
      return { marker, present: corpus.includes(needle), context: markerContext(text, marker) };
    });
    let passed = false;
    if (assertion.type === 'all_of') passed = markers.every((item) => item.present);
    if (assertion.type === 'any_of') passed = markers.some((item) => item.present);
    if (assertion.type === 'none_of') passed = !markers.some((item) => item.present);
    return { id: assertion.id, type: assertion.type, passed, markers };
  }
  const needle = caseSensitive ? assertion.marker : assertion.marker.toLocaleLowerCase('ru-RU');
  const count = corpus.split(needle).length - 1;
  return {
    id: assertion.id,
    type: 'occurrence',
    passed: count >= assertion.min_occurrences,
    marker: assertion.marker,
    observed_occurrences: count,
    min_occurrences: assertion.min_occurrences,
    context: markerContext(text, assertion.marker),
  };
}

function validate(config, contract) {
  if (config.schema_version !== 'liminalqa-monetka-public-rendered-v1') {
    throw new Error(`Unsupported config schema: ${config.schema_version}`);
  }
  if (contract.schema_version !== 'liminalqa-monetka-public-audit-v1') {
    throw new Error(`Unsupported contract schema: ${contract.schema_version}`);
  }
  if (config.navigation.max_parallel !== 1) throw new Error('Rendered audit must remain sequential');
  if (config.navigation.activate_controls !== false || config.navigation.submit_forms !== false) {
    throw new Error('Rendered audit cannot activate controls or submit forms');
  }
  if (contract.boundaries.button_clicks !== false || contract.boundaries.cart_mutation !== false) {
    throw new Error('Contract does not preserve passive browser boundaries');
  }
  const allowedUrls = new Set(contract.allowed_urls);
  const allowedOrigins = new Set(contract.target.allowed_origins);
  for (const target of contract.targets) {
    if (!allowedUrls.has(target.url)) throw new Error(`Target not allowlisted: ${target.url}`);
    if (!allowedOrigins.has(origin(target.url))) throw new Error(`Target origin not allowlisted: ${target.url}`);
  }
  if (!Array.isArray(config.profiles) || config.profiles.length !== 2) {
    throw new Error('Exactly desktop and mobile profiles are required');
  }
}

async function keyboardTrace(page, steps) {
  const trace = [];
  for (let i = 0; i < steps; i += 1) {
    await page.keyboard.press('Tab');
    const current = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element) return null;
      const text = (element.innerText || element.getAttribute('aria-label') || element.getAttribute('title') || '').trim();
      return {
        tag: element.tagName,
        text: text.slice(0, 180),
        href: element instanceof HTMLAnchorElement ? element.href : null,
        type: element.getAttribute('type'),
        name: element.getAttribute('name'),
      };
    });
    trace.push(current);
  }
  return trace;
}

async function observe(browser, contract, config, target, profile, outputDir) {
  const page = await browser.newPage();
  const consoleEntries = [];
  const failedRequests = [];
  const responseErrors = [];

  await page.setViewport(profile.viewport);
  await page.setUserAgent(profile.user_agent);
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.5' });
  page.on('console', (message) => {
    if (consoleEntries.length < config.capture.console_limit) {
      consoleEntries.push({ type: message.type(), text: message.text().slice(0, 1000) });
    }
  });
  page.on('requestfailed', (request) => {
    if (failedRequests.length < config.capture.failed_request_limit) {
      failedRequests.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' });
    }
  });
  page.on('response', (response) => {
    if (response.status() >= 400 && responseErrors.length < config.capture.failed_request_limit) {
      responseErrors.push({ url: response.url(), status: response.status() });
    }
  });

  let navigation = null;
  let error = null;
  try {
    const response = await page.goto(target.url, {
      waitUntil: config.navigation.wait_until,
      timeout: config.navigation.timeout_ms,
    });
    navigation = { status: response?.status() ?? null, requested_url: target.url };
    await new Promise((resolve) => setTimeout(resolve, config.navigation.settle_ms));
  } catch (exc) {
    error = String(exc?.stack || exc);
  }

  const finalUrl = page.url();
  const allowedOrigins = new Set(contract.target.allowed_origins);
  const bounded = (() => {
    try { return allowedOrigins.has(origin(finalUrl)); } catch { return false; }
  })();

  let visibleText = '';
  let structure = null;
  let assertions = target.assertions.map((assertion) => ({
    id: assertion.id, type: assertion.type, passed: false, error: 'navigation_failed',
  }));
  let trace = [];

  if (!error && bounded) {
    visibleText = normalizeText(await page.evaluate(() => document.body?.innerText || ''));
    assertions = target.assertions.map((assertion) => evaluateAssertion(assertion, visibleText));
    structure = await page.evaluate(() => {
      const visible = (element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const interactive = [...document.querySelectorAll('a,button,input,select,textarea,[role="button"]')].filter(visible);
      const unnamed = interactive.filter((element) => {
        const value = (element.innerText || element.getAttribute('aria-label') || element.getAttribute('title') || element.getAttribute('value') || '').trim();
        return !value;
      });
      const images = [...document.images].filter(visible);
      return {
        title: document.title,
        h1_count: document.querySelectorAll('h1').length,
        visible_interactive_count: interactive.length,
        unnamed_visible_interactive_count: unnamed.length,
        visible_image_count: images.length,
        visible_images_missing_alt_count: images.filter((image) => !(image.getAttribute('alt') || '').trim()).length,
        form_count: document.forms.length,
      };
    });
    trace = await keyboardTrace(page, config.capture.keyboard_tab_steps);
  }

  const screenshotName = `${profile.id}-${target.slug}.png`;
  try {
    await page.screenshot({ path: path.join(outputDir, screenshotName), fullPage: config.capture.full_page_screenshot });
  } catch (exc) {
    if (!error) error = `Screenshot failed: ${exc}`;
  }

  await page.close();
  return {
    slug: target.slug,
    role: target.role,
    profile: profile.id,
    requested_url: target.url,
    final_url: finalUrl,
    navigation,
    error,
    final_origin_stayed_bounded: bounded,
    visible_text_sha256: sha256(visibleText),
    visible_text_length: visibleText.length,
    visible_text_sample: visibleText.slice(0, config.capture.visible_text_limit),
    assertions,
    structure,
    keyboard_trace: trace,
    console_entries: consoleEntries,
    failed_requests: failedRequests,
    response_errors: responseErrors,
    screenshot: screenshotName,
  };
}

function buildFindings(contract, observations, profiles) {
  const assertionMap = new Map();
  for (const observation of observations) {
    for (const assertion of observation.assertions) {
      assertionMap.set(`${observation.profile}|${observation.slug}:${assertion.id}`, Boolean(assertion.passed));
    }
  }
  return contract.findings.map((finding) => {
    const passedProfiles = profiles.map((profile) => ({
      profile: profile.id,
      passed: finding.evidence_refs.every((ref) => assertionMap.get(`${profile.id}|${ref}`) === true),
    }));
    const reproduced = passedProfiles.every((item) => item.passed);
    let state = reproduced ? 'CONFIRMED_PRODUCT_DEFECT_CANDIDATE' : 'NEEDS_EVIDENCE';
    if (reproduced && finding.promotion_ceiling) state = finding.promotion_ceiling;
    return {
      id: finding.id,
      title: finding.title,
      severity: finding.severity,
      state,
      evidence_refs: finding.evidence_refs,
      profile_results: passedProfiles,
      promotion_ceiling: finding.promotion_ceiling || null,
      root_cause: 'HYPOTHESIS_ONLY',
      business_impact: 'PLAUSIBLE_NOT_MEASURED',
    };
  });
}

async function main() {
  const args = parseArgs(process.argv);
  const config = readJson(args.config);
  const contract = readJson(args.contract);
  validate(config, contract);
  fs.mkdirSync(args['output-dir'], { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });

  const observations = [];
  try {
    for (const target of contract.targets) {
      for (const profile of config.profiles) {
        observations.push(await observe(browser, contract, config, target, profile, args['output-dir']));
      }
    }
  } finally {
    await browser.close();
  }

  const findings = buildFindings(contract, observations, config.profiles);
  const result = {
    schema_version: RESULT_SCHEMA,
    generated_at: new Date().toISOString(),
    audit_id: contract.audit_id,
    config_audit_id: config.audit_id,
    target: contract.target,
    boundaries: contract.boundaries,
    observations,
    aggregate: {
      expected_observation_count: contract.targets.length * config.profiles.length,
      observed_route_profile_count: observations.length,
      bounded_final_origin_count: observations.filter((item) => item.final_origin_stayed_bounded).length,
      http_2xx_count: observations.filter((item) => item.navigation?.status >= 200 && item.navigation?.status < 300).length,
      findings,
    },
    authority: {
      mode: 'evidence_only',
      grants: { external_submission: false, deployment: false, merge: false },
    },
  };

  fs.writeFileSync(path.join(args['output-dir'], 'monetka-rendered-result.json'), `${JSON.stringify(result, null, 2)}\n`);
  const lines = [
    '# Monetka rendered audit v0.2', '',
    `- Observations: \`${result.aggregate.observed_route_profile_count}/${result.aggregate.expected_observation_count}\``,
    `- HTTP 2xx: \`${result.aggregate.http_2xx_count}\``,
    `- Bounded final origins: \`${result.aggregate.bounded_final_origin_count}\``, '',
    '## Findings', '',
    ...findings.map((finding) => `- **${finding.id}** · ${finding.state} · ${finding.severity} · ${finding.title}`),
  ];
  fs.writeFileSync(path.join(args['output-dir'], 'monetka-rendered-summary.md'), `${lines.join('\n')}\n`);
  console.log(JSON.stringify(result.aggregate, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exit(2);
});
