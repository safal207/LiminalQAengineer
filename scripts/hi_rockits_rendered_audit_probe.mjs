#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

const CONFIG_SCHEMA = 'liminalqa-hi-rockits-public-rendered-v1';
const RESULT_SCHEMA = 'liminalqa-hi-rockits-public-rendered-result-v1';
const ALLOWED_ORIGINS = new Set(['https://rockits.ru', 'https://hirockits.com']);

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith('--') || i + 1 >= argv.length) throw new Error(`Invalid argument: ${key}`);
    args[key.slice(2)] = argv[++i];
  }
  for (const key of ['config', 'contract', 'chrome', 'output-dir']) {
    if (!args[key]) throw new Error(`Missing --${key}`);
  }
  return args;
}

function normalizeText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function stripQuery(rawUrl) {
  try {
    const url = new URL(rawUrl);
    url.search = '';
    url.hash = '';
    return url.toString();
  } catch {
    return String(rawUrl);
  }
}

function context(text, marker, radius = 160) {
  const index = text.toLocaleLowerCase().indexOf(marker.toLocaleLowerCase());
  if (index < 0) return null;
  return text.slice(Math.max(0, index - radius), Math.min(text.length, index + marker.length + radius));
}

function evaluateAssertion(assertion, text) {
  const corpus = assertion.case_sensitive ? text : text.toLocaleLowerCase();
  if (assertion.type === 'all_of' || assertion.type === 'any_of') {
    const markers = assertion.markers.map((marker) => {
      const needle = assertion.case_sensitive ? marker : marker.toLocaleLowerCase();
      return { marker, present: corpus.includes(needle), context: context(text, marker) };
    });
    const passed = assertion.type === 'all_of' ? markers.every((item) => item.present) : markers.some((item) => item.present);
    return { id: assertion.id, type: assertion.type, passed, markers };
  }
  const marker = assertion.marker;
  const needle = assertion.case_sensitive ? marker : marker.toLocaleLowerCase();
  let count = 0;
  let start = 0;
  while ((start = corpus.indexOf(needle, start)) >= 0) {
    count += 1;
    start += Math.max(needle.length, 1);
  }
  return {
    id: assertion.id,
    type: 'occurrence',
    marker,
    observed_occurrences: count,
    min_occurrences: assertion.min_occurrences,
    passed: count >= assertion.min_occurrences,
    context: context(text, marker),
  };
}

function validate(config, contract) {
  if (config.schema_version !== CONFIG_SCHEMA) throw new Error(`Unsupported config schema: ${config.schema_version}`);
  const origins = new Set(contract?.target?.canonical_origins ?? []);
  if (origins.size !== 2 || [...ALLOWED_ORIGINS].some((origin) => !origins.has(origin))) {
    throw new Error('Contract origins are not exactly bounded to the two official Hi, Rockits! origins');
  }
  if (!Array.isArray(config.profiles) || config.profiles.map((p) => p.id).sort().join(',') !== 'desktop,mobile') {
    throw new Error('Exactly desktop and mobile profiles are required');
  }
  if (!Array.isArray(contract.targets) || contract.targets.length !== 4) throw new Error('Exactly four targets are required');
  const boundaries = config.boundaries ?? {};
  for (const key of ['public_pages_only', 'passive_rendering_only', 'keyboard_tab_only']) {
    if (boundaries[key] !== true) throw new Error(`Boundary ${key} must be true`);
  }
  for (const key of ['authentication', 'form_submission', 'button_clicks', 'resume_upload', 'external_contact', 'direct_api_testing', 'active_security_testing', 'load_testing', 'external_submission_authorized', 'deployment_authorized', 'merge_authorized']) {
    if (boundaries[key] !== false) throw new Error(`Boundary ${key} must be false`);
  }
  const allowedPaths = contract.allowed_paths ?? {};
  for (const target of contract.targets) {
    const url = new URL(target.url);
    if (!ALLOWED_ORIGINS.has(url.origin)) throw new Error(`Target outside allowed origins: ${target.url}`);
    if (url.search || url.hash) throw new Error(`Target includes query or fragment: ${target.url}`);
    if (!(allowedPaths[url.origin] ?? []).includes(url.pathname)) throw new Error(`Target path not allowlisted: ${target.url}`);
  }
}

async function keyboardTrace(page, steps) {
  const trace = [];
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press('Tab');
    trace.push(await page.evaluate(() => {
      const el = document.activeElement;
      if (!el) return null;
      return {
        tag: el.tagName?.toLowerCase() ?? null,
        text: (el.innerText || el.getAttribute?.('aria-label') || el.getAttribute?.('title') || '').replace(/\s+/g, ' ').trim().slice(0, 180),
        href: el instanceof HTMLAnchorElement ? el.href : null,
        type: el.getAttribute?.('type') ?? null,
      };
    }));
  }
  return trace;
}

async function observe(browser, config, contract, target, profile, outputDir) {
  const page = await browser.newPage();
  await page.setViewport(profile.viewport);
  await page.setUserAgent(profile.user_agent);
  page.setDefaultNavigationTimeout(config.runtime.navigation_timeout_ms);

  const consoleItems = [];
  const failedRequests = [];
  const badResponses = [];
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type()) && consoleItems.length < config.runtime.max_console_items) {
      consoleItems.push({ type: message.type(), text: message.text().slice(0, 800) });
    }
  });
  page.on('requestfailed', (request) => {
    if (failedRequests.length < config.runtime.max_network_items) {
      failedRequests.push({ url: stripQuery(request.url()), error: request.failure()?.errorText ?? null });
    }
  });
  page.on('response', (response) => {
    if (response.status() >= 400 && badResponses.length < config.runtime.max_network_items) {
      badResponses.push({ url: stripQuery(response.url()), status: response.status() });
    }
  });

  let status = null;
  let navigationError = null;
  try {
    const response = await page.goto(target.url, { waitUntil: 'domcontentloaded' });
    status = response?.status() ?? null;
    await new Promise((resolve) => setTimeout(resolve, config.runtime.settle_ms));
  } catch (error) {
    navigationError = String(error?.message ?? error);
  }

  const finalUrl = page.url();
  const finalOrigin = (() => { try { return new URL(finalUrl).origin; } catch { return null; } })();
  const data = await page.evaluate(() => {
    const bodyText = (document.body?.innerText ?? '').replace(/\s+/g, ' ').trim();
    const named = (el) => (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
    return {
      title: document.title,
      bodyText,
      headings: [...document.querySelectorAll('h1,h2,h3')].slice(0, 100).map((el) => ({ level: el.tagName.toLowerCase(), text: named(el).slice(0, 300) })),
      h1Count: document.querySelectorAll('h1').length,
      formCount: document.forms.length,
      inputCount: document.querySelectorAll('input,textarea,select').length,
      buttonCount: document.querySelectorAll('button,[role="button"]').length,
      linkCount: document.links.length,
      imageCount: document.images.length,
      missingAltCount: [...document.images].filter((img) => !img.hasAttribute('alt') || !img.alt.trim()).length,
      unnamedLinkCount: [...document.querySelectorAll('a')].filter((el) => !named(el) && !el.querySelector('img[alt]')).length,
      duplicateIds: Object.entries([...document.querySelectorAll('[id]')].reduce((acc, el) => { acc[el.id] = (acc[el.id] || 0) + 1; return acc; }, {})).filter(([, count]) => count > 1).slice(0, 50),
    };
  });

  const assertions = target.assertions.map((assertion) => evaluateAssertion(assertion, data.bodyText));
  const trace = await keyboardTrace(page, config.runtime.tab_steps);
  const screenshotName = `${profile.id}-${target.slug}.png`;
  const screenshotPath = path.join(outputDir, screenshotName);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  const screenshotBytes = await fs.readFile(screenshotPath);
  await page.close();

  return {
    slug: target.slug,
    profile: profile.id,
    requested_url: target.url,
    final_url: finalUrl,
    final_origin: finalOrigin,
    origin_stayed_bounded: ALLOWED_ORIGINS.has(finalOrigin),
    status,
    navigation_error: navigationError,
    title: data.title,
    visible_text_length: data.bodyText.length,
    visible_text_sha256: sha256(Buffer.from(data.bodyText)),
    visible_text_sample: data.bodyText.slice(0, 5000),
    assertions,
    structure: {
      headings: data.headings,
      h1_count: data.h1Count,
      form_count: data.formCount,
      input_count: data.inputCount,
      button_count: data.buttonCount,
      link_count: data.linkCount,
      image_count: data.imageCount,
      missing_alt_count: data.missingAltCount,
      unnamed_link_count: data.unnamedLinkCount,
      duplicate_ids: data.duplicateIds,
    },
    keyboard_trace: trace,
    console_items: consoleItems,
    failed_requests: failedRequests,
    bad_responses: badResponses,
    screenshot: { file: screenshotName, sha256: sha256(screenshotBytes), bytes: screenshotBytes.length },
  };
}

function aggregate(contract, observations) {
  const assertionMap = new Map();
  for (const observation of observations) {
    for (const assertion of observation.assertions) {
      assertionMap.set(`${observation.slug}:${observation.profile}:${assertion.id}`, assertion);
    }
  }
  const profiles = ['desktop', 'mobile'];
  const findings = contract.findings.map((finding) => {
    const profilePassed = Object.fromEntries(profiles.map((profile) => [profile, finding.evidence_refs.every((ref) => {
      const [slug, assertionId] = ref.split(':');
      return assertionMap.get(`${slug}:${profile}:${assertionId}`)?.passed === true;
    })]));
    const passedCount = Object.values(profilePassed).filter(Boolean).length;
    const state = passedCount === 2 ? 'CONFIRMED_PRODUCT_DEFECT_CANDIDATE' : passedCount === 1 ? 'PRODUCT_SIGNAL' : 'NEEDS_EVIDENCE';
    return {
      id: finding.id,
      title: finding.title,
      severity: finding.severity,
      state,
      profile_passed: profilePassed,
      evidence_refs: finding.evidence_refs,
      root_cause: 'HYPOTHESIS_ONLY',
      business_impact: 'PLAUSIBLE_NOT_MEASURED',
    };
  });
  return {
    expected_observation_count: contract.targets.length * profiles.length,
    observed_route_profile_count: observations.length,
    bounded_observation_count: observations.filter((o) => o.origin_stayed_bounded).length,
    http_2xx_count: observations.filter((o) => Number.isInteger(o.status) && o.status >= 200 && o.status < 300).length,
    findings,
    decision: findings.some((f) => f.state === 'CONFIRMED_PRODUCT_DEFECT_CANDIDATE') ? 'RENDERED_PRODUCT_DEFECT_CANDIDATES' : 'NEEDS_EVIDENCE',
  };
}

function renderSummary(result) {
  const lines = [
    '# Hi, Rockits! rendered audit v0.2', '',
    `Generated: \`${result.generated_at}\``,
    `- Observations: \`${result.aggregate.observed_route_profile_count}/${result.aggregate.expected_observation_count}\``,
    `- Bounded: \`${result.aggregate.bounded_observation_count}\``,
    `- HTTP 2xx: \`${result.aggregate.http_2xx_count}\``,
    `- Decision: \`${result.aggregate.decision}\``, '', '## Findings', '',
  ];
  for (const finding of result.aggregate.findings) {
    lines.push(`- \`${finding.id}\` · **${finding.severity}** · \`${finding.state}\` — ${finding.title}`);
  }
  lines.push('', '## Authority', '', 'Evidence only. External submission, deployment, and merge remain blocked.', '');
  return lines.join('\n');
}

async function main() {
  const args = parseArgs(process.argv);
  const config = JSON.parse(await fs.readFile(args.config, 'utf8'));
  const contract = JSON.parse(await fs.readFile(args.contract, 'utf8'));
  validate(config, contract);
  await fs.mkdir(args['output-dir'], { recursive: true });
  const browser = await puppeteer.launch({ executablePath: args.chrome, headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const observations = [];
  try {
    for (const target of contract.targets) {
      for (const profile of config.profiles) {
        observations.push(await observe(browser, config, contract, target, profile, args['output-dir']));
      }
    }
  } finally {
    await browser.close();
  }
  const result = {
    schema_version: RESULT_SCHEMA,
    generated_at: new Date().toISOString(),
    audit_id: config.audit_id,
    target: contract.target,
    boundaries: config.boundaries,
    observations,
    aggregate: aggregate(contract, observations),
    authority: { mode: 'evidence_only', grants: { external_submission: false, deployment: false, merge: false } },
  };
  await fs.writeFile(path.join(args['output-dir'], 'hi-rockits-rendered-result.json'), JSON.stringify(result, null, 2));
  await fs.writeFile(path.join(args['output-dir'], 'hi-rockits-rendered-summary.md'), renderSummary(result));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
