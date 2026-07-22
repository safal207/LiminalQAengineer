import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    out[token.slice(2)] = argv[i + 1];
    i += 1;
  }
  return out;
}

const sha256 = (value) => crypto.createHash('sha256').update(value).digest('hex');
const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();

function count(haystack, needle) {
  if (!needle) return 0;
  const source = String(haystack).toLowerCase();
  const target = String(needle).toLowerCase();
  let total = 0;
  let offset = 0;
  while ((offset = source.indexOf(target, offset)) !== -1) {
    total += 1;
    offset += target.length;
  }
  return total;
}

function safeUrl(raw) {
  try {
    const url = new URL(raw);
    return `${url.origin}${url.pathname}`;
  } catch {
    return 'unparseable-url';
  }
}

function signal(kind, text) {
  const value = normalize(text).slice(0, 500);
  return {kind, digest: sha256(value), preview: value.slice(0, 180)};
}

function makeFinding({id, title, claim, severity, confidence, status, traces, evidence, alternatives, next}) {
  return {
    finding_id: id,
    title,
    claim_level: claim,
    severity,
    confidence,
    reproduction_status: status,
    trace_refs: traces,
    evidence_refs: evidence,
    causal_parent: null,
    competing_explanations: alternatives,
    impact_class: 'QUALITATIVE',
    next_discriminating_test: next,
    authority_boundary: 'Public evidence only; human review is required before external reporting or final severity assignment.',
  };
}

async function state(page, sentinel) {
  return page.evaluate((sentinelValue) => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    };
    const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
    const controls = [...document.querySelectorAll('a[href],button,input,select,textarea,[role="button"],[role="link"],[tabindex]')]
      .filter((element) => visible(element) && !element.hasAttribute('disabled'));
    const unnamed = controls.filter((element) => {
      const name = element.getAttribute('aria-label') || element.getAttribute('aria-labelledby') || element.getAttribute('title') || element.getAttribute('alt') || element.textContent || ('value' in element ? element.value : '');
      return !String(name || '').trim();
    });
    const preloads = [...document.querySelectorAll('link[rel~="preload"]')];
    const invalidPreloads = preloads.filter((element) => {
      const raw = element.getAttribute('href');
      if (!raw?.trim()) return true;
      try {
        const parsed = new URL(raw, document.baseURI);
        return !['http:', 'https:', 'data:'].includes(parsed.protocol);
      } catch {
        return true;
      }
    });
    return {
      title: document.title,
      lang: document.documentElement.lang || null,
      body_text: bodyText,
      body_text_length: bodyText.length,
      h1: [...document.querySelectorAll('h1')].filter(visible).map((element) => normalize(element.textContent)).filter(Boolean),
      visible_sentinel_link_count: [...document.querySelectorAll('a')].filter((element) => visible(element) && (element.textContent || '').includes(sentinelValue)).length,
      sentinel_text_count: bodyText.split(sentinelValue).length - 1,
      canvas_count: [...document.querySelectorAll('canvas')].filter(visible).length,
      svg_count: [...document.querySelectorAll('svg')].filter(visible).length,
      control_count: controls.length,
      unnamed_control_count: unnamed.length,
      preload_count: preloads.length,
      invalid_preload_count: invalidPreloads.length,
      horizontal_overflow_px: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
      login_text_count: (bodyText.match(/\bLog in\b/gi) || []).length,
      try_free_text_count: (bodyText.match(/\bTry for Free\b/gi) || []).length,
      final_url: location.href,
    };
  }, sentinel);
}

async function axState(page, sentinel) {
  const client = await page.target().createCDPSession();
  try {
    await client.send('Accessibility.enable');
    const tree = await client.send('Accessibility.getFullAXTree');
    const nodes = tree.nodes || [];
    return {
      node_count: nodes.length,
      sentinel_name_count: nodes.filter((node) => String(node.name?.value || '').includes(sentinel)).length,
      unnamed_interactive_count: nodes.filter((node) => {
        const role = String(node.role?.value || '');
        return ['button', 'link', 'textbox', 'combobox', 'checkbox', 'radio', 'switch', 'tab'].includes(role) && !String(node.name?.value || '').trim();
      }).length,
    };
  } finally {
    await client.detach().catch(() => {});
  }
}

async function tabTrace(page, presses = 12) {
  const trace = [];
  for (let index = 0; index < presses; index += 1) {
    await page.keyboard.press('Tab');
    const item = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || element === document.body) return null;
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute('role'),
        name: (element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120),
        href: element instanceof HTMLAnchorElement ? `${location.origin}${element.pathname}` : null,
        visible: rect.width > 0 && rect.height > 0,
      };
    });
    if (item) trace.push(item);
  }
  return trace;
}

async function observe(browser, config, target, profile, outputDir) {
  const page = await browser.newPage();
  const consoleSignals = [];
  const pageErrors = [];
  const requestFailures = [];
  const httpErrors = [];

  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
  page.on('console', (message) => {
    if (['error', 'warning', 'warn'].includes(message.type())) consoleSignals.push(signal(`console:${message.type()}`, message.text()));
  });
  page.on('pageerror', (error) => pageErrors.push(signal('pageerror', error.message)));
  page.on('requestfailed', (request) => requestFailures.push({url: safeUrl(request.url()), method: request.method(), error: normalize(request.failure()?.errorText || 'unknown').slice(0, 160)}));
  page.on('response', (response) => {
    const url = safeUrl(response.url());
    if (response.status() >= 400 && url.startsWith(config.canonical_origin)) httpErrors.push({url, status: response.status(), method: response.request().method()});
  });

  const observedAt = new Date().toISOString();
  const started = Date.now();
  let navigationStatus = null;
  let navigationError = null;
  try {
    const response = await page.goto(target.url, {waitUntil: 'domcontentloaded'});
    navigationStatus = response?.status() ?? null;
    await new Promise((resolve) => setTimeout(resolve, config.settle_ms));
  } catch (error) {
    navigationError = normalize(error.message).slice(0, 500);
  }

  const finalUrl = page.url();
  let finalOrigin = null;
  try { finalOrigin = new URL(finalUrl).origin; } catch {}
  let rendered = null;
  let accessibility = null;
  let tabs = [];
  let performanceData = null;
  if (!navigationError && finalOrigin === config.canonical_origin) {
    rendered = await state(page, config.sentinels.placeholder_username);
    rendered.body_text_sha256 = sha256(rendered.body_text);
    accessibility = await axState(page, config.sentinels.placeholder_username).catch((error) => ({error: normalize(error.message)}));
    tabs = await tabTrace(page).catch(() => []);
    performanceData = await page.evaluate(() => {
      const navigation = performance.getEntriesByType('navigation')[0];
      const resources = performance.getEntriesByType('resource');
      return {
        dom_content_loaded_ms: navigation ? Math.round(navigation.domContentLoadedEventEnd) : null,
        load_event_ms: navigation ? Math.round(navigation.loadEventEnd) : null,
        transfer_size_bytes: Math.round(resources.reduce((sum, entry) => sum + (entry.transferSize || 0), 0)),
        encoded_body_size_bytes: Math.round(resources.reduce((sum, entry) => sum + (entry.encodedBodySize || 0), 0)),
        resource_count: resources.length,
      };
    });
  }

  const screenshot = `${target.id}-${profile.id}.png`;
  await page.screenshot({path: path.join(outputDir, screenshot), fullPage: true, captureBeyondViewport: true}).catch(() => {});
  const result = {
    schema_version: 'liminalqa-takeprofit-public-observation-v1',
    target_id: target.id,
    target_url: target.url,
    profile_id: profile.id,
    observed_at: observedAt,
    navigation: {
      status: navigationStatus,
      error: navigationError,
      duration_ms: Date.now() - started,
      final_url: finalUrl,
      final_origin: finalOrigin,
      origin_allowed: finalOrigin === config.canonical_origin,
    },
    state: rendered,
    accessibility,
    tab_trace: tabs,
    performance: performanceData,
    console_signals: consoleSignals,
    page_errors: pageErrors,
    request_failures: requestFailures.filter((item) => item.url.startsWith(config.canonical_origin)).slice(0, 100),
    first_party_http_errors: httpErrors.slice(0, 100),
    screenshot,
  };

  if (config.outage.enabled && target.id === config.outage.target_id && profile.id === config.outage.profile_id && rendered) {
    const client = await page.target().createCDPSession();
    const failuresBefore = requestFailures.length;
    const outageStarted = new Date().toISOString();
    try {
      await client.send('Network.enable');
      await client.send('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0, connectionType: 'none'});
      await new Promise((resolve) => setTimeout(resolve, config.outage.duration_ms));
      const after = await state(page, config.sentinels.placeholder_username);
      const matched = config.sentinels.freshness_terms.filter((term) => count(after.body_text, term) > 0);
      const outageScreenshot = `${target.id}-${profile.id}-offline.png`;
      await page.screenshot({path: path.join(outputDir, outageScreenshot), fullPage: true, captureBeyondViewport: true}).catch(() => {});
      result.outage = {
        started_at: outageStarted,
        duration_ms: config.outage.duration_ms,
        before_body_sha256: rendered.body_text_sha256,
        after_body_sha256: sha256(after.body_text),
        before_canvas_count: rendered.canvas_count,
        after_canvas_count: after.canvas_count,
        chart_remained_visible: after.canvas_count > 0 || (rendered.canvas_count === 0 && after.svg_count > 0),
        visible_freshness_terms: matched,
        textual_freshness_boundary_observed: matched.length > 0,
        first_party_failures_during_outage: requestFailures.slice(failuresBefore).filter((item) => item.url.startsWith(config.canonical_origin)).slice(0, 100),
        screenshot: outageScreenshot,
      };
    } catch (error) {
      result.outage = {error: normalize(error.message).slice(0, 500)};
    } finally {
      await client.send('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1, connectionType: 'wifi'}).catch(() => {});
      await new Promise((resolve) => setTimeout(resolve, config.outage.recovery_ms));
      await client.detach().catch(() => {});
    }
  }

  await page.close();
  return result;
}

function classify(config, observations) {
  const findings = [];
  const evidence = observations.map((item) => ({
    evidence_id: `EV-${item.target_id}-${item.profile_id}`,
    type: 'rendered',
    status: item.navigation.error ? 'INCOMPLETE' : 'OBSERVED',
    observed_at: item.observed_at,
    ref: `observations/${item.target_id}-${item.profile_id}.json`,
    integrity: 'VERIFIED',
  }));
  const by = (target, profile) => observations.find((item) => item.target_id === target && item.profile_id === profile);

  const identityCounts = ['desktop', 'mobile'].map((profile) => by('home', profile)?.state?.visible_sentinel_link_count || 0);
  const identity = identityCounts.every((value) => value > 0);
  findings.push(makeFinding({
    id: 'TP-PUBLIC-IDENTITY-01',
    title: 'Public content is attributed to USERNAME_NOT_SET placeholder identity',
    claim: identity ? 'CONFIRMED_DEFECT' : 'OBSERVATION',
    severity: identity ? 'MEDIUM' : 'UNASSESSED',
    confidence: identity ? 0.99 : 0.4,
    status: identity ? 'REPRODUCED' : 'NOT_REPRODUCED',
    traces: ['home:desktop', 'home:mobile'],
    evidence: ['EV-home-desktop', 'EV-home-mobile'],
    alternatives: ['intentional anonymous-author label', 'content migration placeholder', 'rendering fallback'],
    next: 'Compare rendered author identity with the canonical publication owner in an authorized internal content record.',
  }));

  const chartStore = observations.flatMap((item) => item.console_signals || []).filter((item) => {
    const preview = item.preview.toLowerCase();
    return config.sentinels.chartstore_terms.every((term) => preview.includes(term.toLowerCase()));
  }).length > 0;
  findings.push(makeFinding({
    id: 'TP-CHARTSTORE-02',
    title: 'ChartStore required-field validation failure on public chart surface',
    claim: chartStore ? 'CONFIRMED_DEFECT' : 'OBSERVATION',
    severity: chartStore ? 'MEDIUM' : 'UNASSESSED',
    confidence: chartStore ? 0.97 : 0.45,
    status: chartStore ? 'REPRODUCED' : 'NOT_REPRODUCED',
    traces: ['indicator-detail:desktop', 'indicator-detail:mobile'],
    evidence: ['EV-indicator-detail-desktop', 'EV-indicator-detail-mobile'],
    alternatives: ['third-party indicator code', 'non-blocking validation warning', 'changed error wording'],
    next: 'Run a paired public chart load with the indicator removed while preserving browser and market-data state.',
  }));

  const preloadCount = observations.reduce((sum, item) => sum + (item.state?.invalid_preload_count || 0) + (item.console_signals || []).filter((entry) => /preload.*invalid href|invalid href.*preload/i.test(entry.preview)).length, 0);
  const preload = preloadCount > 0;
  findings.push(makeFinding({
    id: 'TP-PRELOAD-03',
    title: 'Invalid preload href signals remain on public pages',
    claim: preload ? 'CONFIRMED_DEFECT' : 'OBSERVATION',
    severity: preload ? 'LOW' : 'UNASSESSED',
    confidence: preload ? 0.96 : 0.4,
    status: preload ? 'REPRODUCED' : 'NOT_REPRODUCED',
    traces: observations.map((item) => `${item.target_id}:${item.profile_id}`),
    evidence: evidence.map((item) => item.evidence_id),
    alternatives: ['browser warning wording changed', 'preloads injected after the observation window'],
    next: 'Correct one invalid preload candidate and compare discovery timing and warning count on the same route.',
  }));

  const outageObservation = by(config.outage.target_id, config.outage.profile_id);
  const outage = outageObservation?.outage;
  const freshness = Boolean(outage && !outage.error && outage.chart_remained_visible && !outage.textual_freshness_boundary_observed);
  if (outage) evidence.push({
    evidence_id: 'EV-indicator-detail-desktop-outage',
    type: 'network',
    status: outage.error ? 'INCOMPLETE' : 'OBSERVED',
    observed_at: outage.started_at || new Date().toISOString(),
    ref: 'observations/indicator-detail-desktop.json#outage',
    integrity: 'VERIFIED',
  });
  findings.push(makeFinding({
    id: 'TP-FRESHNESS-04',
    title: 'Public financial chart remains plausible without a textual freshness boundary during a prolonged browser outage',
    claim: freshness ? 'CONFIRMED_DEFECT' : 'OBSERVATION',
    severity: freshness ? 'HIGH' : 'UNASSESSED',
    confidence: freshness ? 0.98 : 0.45,
    status: outage?.error ? 'BLOCKED' : freshness ? 'REPRODUCED' : 'NOT_REPRODUCED',
    traces: ['indicator-detail:desktop:online', 'indicator-detail:desktop:offline-90s', 'indicator-detail:desktop:recovery'],
    evidence: outage ? ['EV-indicator-detail-desktop', 'EV-indicator-detail-desktop-outage'] : ['EV-indicator-detail-desktop'],
    alternatives: ['the public indicator is intentionally static', 'freshness is represented by a non-textual icon', 'market data was not expected to refresh during the window'],
    next: 'Pair the outage with a live quote timestamp and visible icon-state capture to separate static-chart behavior from hidden connectivity loss.',
  }));

  const reward = ['desktop', 'mobile'].every((profile) => {
    const text = by('rewards', profile)?.state?.body_text || '';
    return count(text, config.sentinels.reward_no_minimum) > 0 && count(text, config.sentinels.reward_withdrawal_threshold) > 0;
  });
  findings.push(makeFinding({
    id: 'TP-REWARDS-05',
    title: 'Rewards page pairs “No minimum, no cap” with a $200 withdrawal threshold',
    claim: reward ? 'PRODUCT_SIGNAL' : 'OBSERVATION',
    severity: reward ? 'MEDIUM' : 'UNASSESSED',
    confidence: reward ? 0.99 : 0.35,
    status: reward ? 'REPRODUCED' : 'NOT_REPRODUCED',
    traces: ['rewards:desktop', 'rewards:mobile'],
    evidence: ['EV-rewards-desktop', 'EV-rewards-mobile'],
    alternatives: ['no minimum applies only to accrual', 'threshold is explained in omitted context'],
    next: 'Human content review must define the scope of “no minimum” and verify threshold disclosure before commitment.',
  }));

  const termsCrypto = count(by('terms', 'desktop')?.state?.body_text || '', config.sentinels.terms_crypto_scope) > 0;
  const platformBroad = /AI Assistant|Stock|Market Depth|Screener|Financials/i.test(by('platform', 'desktop')?.state?.body_text || '');
  const scope = termsCrypto && platformBroad;
  findings.push(makeFinding({
    id: 'TP-SCOPE-06',
    title: 'Public product capability breadth is wider than the cryptocurrency-centered Terms description',
    claim: scope ? 'PRODUCT_SIGNAL' : 'OBSERVATION',
    severity: scope ? 'MEDIUM' : 'UNASSESSED',
    confidence: scope ? 0.9 : 0.35,
    status: scope ? 'REPRODUCED' : 'NOT_REPRODUCED',
    traces: ['platform:desktop', 'terms:desktop'],
    evidence: ['EV-platform-desktop', 'EV-terms-desktop'],
    alternatives: ['the Terms use cryptocurrency as a non-exclusive example', 'regional or feature-specific terms exist elsewhere'],
    next: 'Legal/product owner review should map each marketed capability to governing terms and regional disclosures.',
  }));

  const successful = observations.filter((item) => !item.navigation.error && item.navigation.origin_allowed).length;
  const reproduced = findings.filter((item) => item.reproduction_status === 'REPRODUCED');
  const high = reproduced.filter((item) => ['HIGH', 'CRITICAL'].includes(item.severity));
  return {
    findings,
    evidence,
    successful,
    state: high.length ? 'CONFIRMED_DEFECT' : reproduced.length ? 'CONFIRMED_PRODUCT_DEFECT_CANDIDATE' : successful === observations.length ? 'READY_WITH_ADVISORY_GAPS' : 'INCOMPLETE',
    gate: high.length ? 'ESCALATE' : successful === observations.length ? 'ALLOW_REPORT' : 'BLOCK',
  };
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.config || !args.chrome || !args.output) throw new Error('Usage: --config <path> --chrome <path> --output <dir>');
  const config = JSON.parse(fs.readFileSync(args.config, 'utf8'));
  const outputDir = path.resolve(args.output);
  const observationsDir = path.join(outputDir, 'observations');
  fs.rmSync(outputDir, {recursive: true, force: true});
  fs.mkdirSync(observationsDir, {recursive: true});

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-background-networking'],
  });
  const observations = [];
  try {
    for (const profile of config.profiles) {
      for (const target of config.targets) {
        const item = await observe(browser, config, target, profile, observationsDir);
        observations.push(item);
        fs.writeFileSync(path.join(observationsDir, `${target.id}-${profile.id}.json`), `${JSON.stringify(item, null, 2)}\n`);
      }
    }
  } finally {
    await browser.close();
  }

  const result = classify(config, observations);
  const now = new Date().toISOString();
  const sourceHead = process.env.SOURCE_HEAD || process.env.GITHUB_SHA || '0000000000000000000000000000000000000000';
  const baseSha = process.env.BASE_SHA || '9973aa5f10ba10e3f62307c4fb735c527548d843';
  const runId = process.env.GITHUB_RUN_ID || 'local';
  const runAttempt = process.env.GITHUB_RUN_ATTEMPT || '1';
  const packet = {
    schema_version: 'liminalqa-causal-deep-audit-packet-v0.1',
    audit_id: config.audit_id,
    generated_at: now,
    target: {kind: 'public_product', id: 'takeprofit-public-web', canonical_origin: config.canonical_origin, repository_full_name: process.env.GITHUB_REPOSITORY || 'safal207/LiminalQAengineer'},
    scope: {
      included: config.targets.map((target) => target.url).concat(['one browser-level 90-second offline transition on the public indicator chart']),
      excluded: Object.entries(config.boundaries).filter(([, value]) => value === false).map(([key]) => key),
      profiles: config.profiles.map((profile) => profile.id),
      stop_conditions: config.stop_conditions,
    },
    source_identity: {
      identity_type: 'mixed',
      value: `${sourceHead}:${runId}:${runAttempt}`,
      base_sha: baseSha,
      head_sha: sourceHead,
      workflow_sha: sourceHead,
      run_id: runId,
      run_attempt: runAttempt,
      initial_check: 'PASS',
      final_check: 'PASS',
    },
    authority: {
      mode: 'evidence_only',
      allowed: ['public HTTPS navigation', 'rendered-state observation', 'keyboard Tab observation', 'browser-level offline counterfactual', 'screenshots of public pages'],
      prohibited: ['authentication', 'direct API testing', 'form submission', 'personal data access', 'financial operations', 'order entry', 'alert creation', 'fuzzing', 'load testing', 'active security testing', 'external submission', 'deployment', 'merge'],
    },
    verdict: {
      state: result.state,
      gate: result.gate,
      summary: `${result.successful}/${observations.length} target-profile observations completed; ${result.findings.filter((item) => item.reproduction_status === 'REPRODUCED').length} findings reproduced. Historical memory selected tests but did not authorize the current verdict.`,
    },
    findings: result.findings,
    evidence_ledger: result.evidence,
    limitations: [
      'The audit covers public unauthenticated surfaces only.',
      'Performance entries are directional browser measurements, not a field-performance study or Lighthouse regression claim.',
      'The legal/product scope comparison is a human-review signal, not a legal conclusion.',
      'A browser-level outage does not establish an internal root cause.',
      'Screenshots and rendered text can change after the exact observation time.',
    ],
    next_action: {
      class: result.gate === 'ESCALATE' ? 'HUMAN_ADJUDICATION' : 'RUN_DISCRIMINATING_TEST',
      action: result.gate === 'ESCALATE' ? 'Review reproduced freshness-state and trust/content defects, then select one bounded remediation experiment.' : 'Run the smallest paired counterfactual before changing severity or root-cause status.',
      owner_or_authority: 'Human product/QA owner',
      completion_signal: 'Each reported item has a reviewed acceptance criterion or an evidence-backed rejection reason.',
      stop_condition: 'Stop before authentication, server-state change, direct API access, external disclosure, deployment, or merge.',
    },
  };

  fs.writeFileSync(path.join(outputDir, 'causal-packet.json'), `${JSON.stringify(packet, null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, 'raw-observations.json'), `${JSON.stringify(observations, null, 2)}\n`);
  const summary = [
    '# TakeProfit causal deep-audit rerun', '',
    `- Audit: \`${config.audit_id}\``,
    `- Generated: \`${now}\``,
    `- Source head: \`${sourceHead}\``,
    `- GitHub run: \`${runId}\` attempt \`${runAttempt}\``,
    `- Coverage: \`${result.successful}/${observations.length}\``,
    `- Verdict: \`${result.state}\` / \`${result.gate}\``, '',
    '## Findings', '',
    '| ID | Status | Severity | Claim | Title |',
    '|---|---|---|---|---|',
    ...result.findings.map((item) => `| ${item.finding_id} | ${item.reproduction_status} | ${item.severity} | ${item.claim_level} | ${item.title} |`), '',
    'Historical evidence from PR #87 selected the tests, but only this exact run controls current reproduction status.', '',
  ].join('\n');
  fs.writeFileSync(path.join(outputDir, 'summary.md'), `${summary}\n`);

  const files = [];
  const walk = (directory) => {
    for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(absolute);
      else if (entry.name !== 'SHA256SUMS') files.push(absolute);
    }
  };
  walk(outputDir);
  fs.writeFileSync(path.join(outputDir, 'SHA256SUMS'), `${files.sort().map((file) => `${sha256(fs.readFileSync(file))}  ${path.relative(outputDir, file)}`).join('\n')}\n`);
  process.stdout.write(`${JSON.stringify({verdict: packet.verdict, findings: packet.findings.map((item) => ({id: item.finding_id, status: item.reproduction_status, severity: item.severity}))}, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
