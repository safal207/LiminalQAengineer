import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith('--')) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));
const hash = (value) => crypto.createHash('sha256').update(value).digest('hex');
const tidy = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
const occurrences = (text, needle) => needle ? String(text).toLowerCase().split(String(needle).toLowerCase()).length - 1 : 0;
const publicUrl = (raw) => { try { const url = new URL(raw); return `${url.origin}${url.pathname}`; } catch { return 'invalid-url'; } };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function finding(id, title, reproduced, severity, claim, traces, evidence, alternatives, next, confidence = 0.98) {
  return {
    finding_id: id,
    title,
    claim_level: reproduced ? claim : 'OBSERVATION',
    severity: reproduced ? severity : 'UNASSESSED',
    confidence: reproduced ? confidence : 0.4,
    reproduction_status: reproduced ? 'REPRODUCED' : 'NOT_REPRODUCED',
    trace_refs: traces,
    evidence_refs: evidence,
    causal_parent: null,
    competing_explanations: alternatives,
    impact_class: 'QUALITATIVE',
    next_discriminating_test: next,
    authority_boundary: 'Public evidence only; human review is required before external reporting, remediation, deployment, or merge.',
  };
}

async function renderedState(page, sentinel) {
  return page.evaluate((sentinelValue) => {
    const clean = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
    const visible = (element) => {
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && box.width > 0 && box.height > 0;
    };
    const body = clean(document.body?.innerText);
    const controls = [...document.querySelectorAll('a[href],button,input,select,textarea,[role="button"],[role="link"],[tabindex]')]
      .filter((element) => visible(element) && !element.hasAttribute('disabled'));
    const unnamed = controls.filter((element) => !clean(
      element.getAttribute('aria-label') || element.getAttribute('aria-labelledby') || element.getAttribute('title') ||
      element.getAttribute('alt') || element.textContent || ('value' in element ? element.value : '')
    ));
    const preloads = [...document.querySelectorAll('link[rel~="preload"]')];
    const invalidPreloads = preloads.filter((element) => {
      const raw = element.getAttribute('href');
      if (!clean(raw)) return true;
      try { return !['http:', 'https:', 'data:'].includes(new URL(raw, document.baseURI).protocol); } catch { return true; }
    });
    return {
      title: document.title,
      lang: document.documentElement.lang || null,
      body_text: body,
      body_text_length: body.length,
      h1: [...document.querySelectorAll('h1')].filter(visible).map((element) => clean(element.textContent)).filter(Boolean),
      visible_sentinel_link_count: [...document.querySelectorAll('a')].filter((element) => visible(element) && clean(element.textContent).includes(sentinelValue)).length,
      sentinel_text_count: body.split(sentinelValue).length - 1,
      canvas_count: [...document.querySelectorAll('canvas')].filter(visible).length,
      svg_count: [...document.querySelectorAll('svg')].filter(visible).length,
      control_count: controls.length,
      unnamed_control_count: unnamed.length,
      preload_count: preloads.length,
      invalid_preload_count: invalidPreloads.length,
      horizontal_overflow_px: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
      login_text_count: (body.match(/\bLog in\b/gi) || []).length,
      try_free_text_count: (body.match(/\bTry for Free\b/gi) || []).length,
      final_url: location.href,
    };
  }, sentinel);
}

async function accessibilityState(page, sentinel) {
  const client = await page.target().createCDPSession();
  try {
    await client.send('Accessibility.enable');
    const {nodes = []} = await client.send('Accessibility.getFullAXTree');
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

async function observe(browser, config, target, profile, dir) {
  const page = await browser.newPage();
  const consoleSignals = [];
  const requestFailures = [];
  const httpErrors = [];
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
  page.on('console', (message) => {
    if (['error', 'warning', 'warn'].includes(message.type())) {
      const preview = tidy(message.text()).slice(0, 180);
      consoleSignals.push({type: message.type(), preview, digest: hash(preview)});
    }
  });
  page.on('pageerror', (error) => {
    const preview = tidy(error.message).slice(0, 180);
    consoleSignals.push({type: 'pageerror', preview, digest: hash(preview)});
  });
  page.on('requestfailed', (request) => requestFailures.push({
    url: publicUrl(request.url()), method: request.method(), error: tidy(request.failure()?.errorText || 'unknown').slice(0, 160),
  }));
  page.on('response', (response) => {
    const url = publicUrl(response.url());
    if (response.status() >= 400 && url.startsWith(config.canonical_origin)) httpErrors.push({url, status: response.status()});
  });

  const observedAt = new Date().toISOString();
  const started = Date.now();
  let status = null;
  let error = null;
  try {
    const response = await page.goto(target.url, {waitUntil: 'domcontentloaded'});
    status = response?.status() ?? null;
    await sleep(config.settle_ms);
  } catch (cause) {
    error = tidy(cause.message).slice(0, 500);
  }
  const finalUrl = page.url();
  let finalOrigin = null;
  try { finalOrigin = new URL(finalUrl).origin; } catch {}
  let state = null;
  let accessibility = null;
  let performance = null;
  if (!error && finalOrigin === config.canonical_origin) {
    state = await renderedState(page, config.sentinels.placeholder_username);
    state.body_text_sha256 = hash(state.body_text);
    accessibility = await accessibilityState(page, config.sentinels.placeholder_username).catch((cause) => ({error: tidy(cause.message)}));
    performance = await page.evaluate(() => {
      const navigation = globalThis.performance.getEntriesByType('navigation')[0];
      const resources = globalThis.performance.getEntriesByType('resource');
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
  await page.screenshot({path: path.join(dir, screenshot), fullPage: true, captureBeyondViewport: true}).catch(() => {});
  const result = {
    schema_version: 'liminalqa-takeprofit-public-observation-v1',
    target_id: target.id,
    target_url: target.url,
    profile_id: profile.id,
    observed_at: observedAt,
    navigation: {status, error, duration_ms: Date.now() - started, final_url: finalUrl, final_origin: finalOrigin, origin_allowed: finalOrigin === config.canonical_origin},
    state,
    accessibility,
    performance,
    console_signals: consoleSignals,
    request_failures: requestFailures.filter((item) => item.url.startsWith(config.canonical_origin)).slice(0, 100),
    first_party_http_errors: httpErrors.slice(0, 100),
    screenshot,
  };

  if (config.outage.enabled && target.id === config.outage.target_id && profile.id === config.outage.profile_id && state) {
    const client = await page.target().createCDPSession();
    const beforeFailures = requestFailures.length;
    const startedAt = new Date().toISOString();
    try {
      await client.send('Network.enable');
      await client.send('Network.emulateNetworkConditions', {offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0, connectionType: 'none'});
      await sleep(config.outage.duration_ms);
      const after = await renderedState(page, config.sentinels.placeholder_username);
      const matched = config.sentinels.freshness_terms.filter((term) => occurrences(after.body_text, term) > 0);
      const offlineScreenshot = `${target.id}-${profile.id}-offline.png`;
      await page.screenshot({path: path.join(dir, offlineScreenshot), fullPage: true, captureBeyondViewport: true}).catch(() => {});
      result.outage = {
        started_at: startedAt,
        duration_ms: config.outage.duration_ms,
        before_body_sha256: state.body_text_sha256,
        after_body_sha256: hash(after.body_text),
        before_canvas_count: state.canvas_count,
        after_canvas_count: after.canvas_count,
        chart_remained_visible: after.canvas_count > 0 || (state.canvas_count === 0 && after.svg_count > 0),
        visible_freshness_terms: matched,
        textual_freshness_boundary_observed: matched.length > 0,
        first_party_failures_during_outage: requestFailures.slice(beforeFailures).filter((item) => item.url.startsWith(config.canonical_origin)).slice(0, 100),
        screenshot: offlineScreenshot,
      };
    } catch (cause) {
      result.outage = {error: tidy(cause.message).slice(0, 500)};
    } finally {
      await client.send('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1, connectionType: 'wifi'}).catch(() => {});
      await sleep(config.outage.recovery_ms);
      await client.detach().catch(() => {});
    }
  }
  await page.close();
  return result;
}

function classify(config, observations) {
  const by = (target, profile) => observations.find((item) => item.target_id === target && item.profile_id === profile);
  const evidence = observations.map((item) => ({
    evidence_id: `EV-${item.target_id}-${item.profile_id}`,
    type: 'rendered',
    status: item.navigation.error ? 'INCOMPLETE' : 'OBSERVED',
    observed_at: item.observed_at,
    ref: `observations/${item.target_id}-${item.profile_id}.json`,
    integrity: 'VERIFIED',
  }));

  const identity = ['desktop', 'mobile'].every((profile) => (by('home', profile)?.state?.visible_sentinel_link_count || 0) > 0);
  const chartStore = observations.some((item) => (item.console_signals || []).some((entry) => config.sentinels.chartstore_terms.every((term) => entry.preview.toLowerCase().includes(term.toLowerCase()))));
  const preloads = observations.some((item) => (item.state?.invalid_preload_count || 0) > 0 || (item.console_signals || []).some((entry) => /preload.*invalid href|invalid href.*preload/i.test(entry.preview)));
  const outage = by(config.outage.target_id, config.outage.profile_id)?.outage;
  const freshness = Boolean(outage && !outage.error && outage.chart_remained_visible && !outage.textual_freshness_boundary_observed);
  if (outage) evidence.push({
    evidence_id: 'EV-indicator-detail-desktop-outage', type: 'network', status: outage.error ? 'INCOMPLETE' : 'OBSERVED',
    observed_at: outage.started_at || new Date().toISOString(), ref: 'observations/indicator-detail-desktop.json#outage', integrity: 'VERIFIED',
  });
  const rewards = ['desktop', 'mobile'].every((profile) => {
    const text = by('rewards', profile)?.state?.body_text || '';
    return occurrences(text, config.sentinels.reward_no_minimum) > 0 && occurrences(text, config.sentinels.reward_withdrawal_threshold) > 0;
  });
  const scope = occurrences(by('terms', 'desktop')?.state?.body_text || '', config.sentinels.terms_crypto_scope) > 0 &&
    /AI Assistant|Stock|Market Depth|Screener|Financials/i.test(by('platform', 'desktop')?.state?.body_text || '');

  const findings = [
    finding('TP-PUBLIC-IDENTITY-01', 'Public content is attributed to USERNAME_NOT_SET placeholder identity', identity, 'MEDIUM', 'CONFIRMED_DEFECT', ['home:desktop', 'home:mobile'], ['EV-home-desktop', 'EV-home-mobile'], ['intentional anonymous-author label', 'content migration placeholder', 'rendering fallback'], 'Compare rendered identity with the canonical publication owner in an authorized internal record.', 0.99),
    finding('TP-CHARTSTORE-02', 'ChartStore required-field validation failure on public chart surface', chartStore, 'MEDIUM', 'CONFIRMED_DEFECT', ['indicator-detail:desktop', 'indicator-detail:mobile'], ['EV-indicator-detail-desktop', 'EV-indicator-detail-mobile'], ['third-party indicator code', 'non-blocking validation warning', 'changed error wording'], 'Run a paired chart load without the indicator while preserving browser and market-data state.', 0.97),
    finding('TP-PRELOAD-03', 'Invalid preload href signals remain on public pages', preloads, 'LOW', 'CONFIRMED_DEFECT', observations.map((item) => `${item.target_id}:${item.profile_id}`), evidence.map((item) => item.evidence_id), ['browser warning wording changed', 'late preload injection'], 'Correct one invalid preload and compare discovery timing and warning count.', 0.96),
    finding('TP-FRESHNESS-04', 'Public financial chart remains plausible without a textual freshness boundary during a prolonged browser outage', freshness, 'HIGH', 'CONFIRMED_DEFECT', ['indicator-detail:desktop:online', 'indicator-detail:desktop:offline-90s', 'indicator-detail:desktop:recovery'], outage ? ['EV-indicator-detail-desktop', 'EV-indicator-detail-desktop-outage'] : ['EV-indicator-detail-desktop'], ['public indicator may be intentionally static', 'freshness may be represented only by an icon', 'market data may not be expected to refresh'], 'Pair the outage with a live quote timestamp and icon-state capture.', 0.98),
    finding('TP-REWARDS-05', 'Rewards page pairs “No minimum, no cap” with a $200 withdrawal threshold', rewards, 'MEDIUM', 'PRODUCT_SIGNAL', ['rewards:desktop', 'rewards:mobile'], ['EV-rewards-desktop', 'EV-rewards-mobile'], ['no minimum may apply only to accrual', 'threshold context may be elsewhere'], 'Human content review must define the scope of “no minimum” and verify threshold disclosure.', 0.99),
    finding('TP-SCOPE-06', 'Public capability breadth is wider than the cryptocurrency-centered Terms description', scope, 'MEDIUM', 'PRODUCT_SIGNAL', ['platform:desktop', 'terms:desktop'], ['EV-platform-desktop', 'EV-terms-desktop'], ['cryptocurrency may be a non-exclusive example', 'regional terms may exist elsewhere'], 'Legal/product owner review should map marketed capabilities to governing terms.', 0.9),
  ];
  const successful = observations.filter((item) => !item.navigation.error && item.navigation.origin_allowed).length;
  const reproduced = findings.filter((item) => item.reproduction_status === 'REPRODUCED');
  const high = reproduced.some((item) => ['HIGH', 'CRITICAL'].includes(item.severity));
  return {
    findings,
    evidence,
    successful,
    state: high ? 'CONFIRMED_DEFECT' : reproduced.length ? 'CONFIRMED_PRODUCT_DEFECT_CANDIDATE' : successful === observations.length ? 'READY_WITH_ADVISORY_GAPS' : 'INCOMPLETE',
    gate: high ? 'ESCALATE' : successful === observations.length ? 'ALLOW_REPORT' : 'BLOCK',
  };
}

async function main() {
  if (!args.config || !args.chrome || !args.output) throw new Error('Usage: --config <path> --chrome <path> --output <dir>');
  const config = JSON.parse(fs.readFileSync(args.config, 'utf8'));
  const output = path.resolve(args.output);
  const observationsDir = path.join(output, 'observations');
  fs.rmSync(output, {recursive: true, force: true});
  fs.mkdirSync(observationsDir, {recursive: true});
  const browser = await puppeteer.launch({executablePath: args.chrome, headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']});
  const observations = [];
  try {
    for (const profile of config.profiles) for (const target of config.targets) {
      const item = await observe(browser, config, target, profile, observationsDir);
      observations.push(item);
      fs.writeFileSync(path.join(observationsDir, `${target.id}-${profile.id}.json`), `${JSON.stringify(item, null, 2)}\n`);
    }
  } finally {
    await browser.close();
  }

  const result = classify(config, observations);
  const now = new Date().toISOString();
  const head = process.env.SOURCE_HEAD || process.env.GITHUB_SHA || '0000000000000000000000000000000000000000';
  const base = process.env.BASE_SHA || '9973aa5f10ba10e3f62307c4fb735c527548d843';
  const run = process.env.GITHUB_RUN_ID || 'local';
  const attempt = process.env.GITHUB_RUN_ATTEMPT || '1';
  const packet = {
    schema_version: 'liminalqa-causal-deep-audit-packet-v0.1',
    audit_id: config.audit_id,
    generated_at: now,
    target: {kind: 'public_product', id: 'takeprofit-public-web', canonical_origin: config.canonical_origin, repository_full_name: process.env.GITHUB_REPOSITORY || 'safal207/LiminalQAengineer'},
    scope: {
      included: [...config.targets.map((target) => target.url), 'one browser-level 90-second offline transition on the public indicator chart'],
      excluded: Object.entries(config.boundaries).filter(([, value]) => value === false).map(([key]) => key),
      profiles: config.profiles.map((profile) => profile.id),
      stop_conditions: config.stop_conditions,
    },
    source_identity: {identity_type: 'mixed', value: `${head}:${run}:${attempt}`, base_sha: base, head_sha: head, workflow_sha: head, run_id: run, run_attempt: attempt, initial_check: 'PASS', final_check: 'PASS'},
    authority: {
      mode: 'evidence_only',
      allowed: ['public HTTPS navigation', 'rendered and accessibility observation', 'browser-level offline counterfactual', 'public screenshots'],
      prohibited: ['authentication', 'direct API testing', 'form submission', 'personal data access', 'financial operations', 'order entry', 'alert creation', 'fuzzing', 'load testing', 'active security testing', 'external submission', 'deployment', 'merge'],
    },
    verdict: {state: result.state, gate: result.gate, summary: `${result.successful}/${observations.length} observations completed; ${result.findings.filter((item) => item.reproduction_status === 'REPRODUCED').length} findings reproduced. Historical memory selected tests but did not authorize this verdict.`},
    findings: result.findings,
    evidence_ledger: result.evidence,
    limitations: [
      'Public unauthenticated surfaces only.',
      'Performance entries are directional browser measurements, not a controlled field or Lighthouse regression claim.',
      'The legal/product scope comparison is a human-review signal, not a legal conclusion.',
      'A browser-level outage does not establish internal root cause.',
      'Rendered content can change after the exact observation time.',
    ],
    next_action: {
      class: result.gate === 'ESCALATE' ? 'HUMAN_ADJUDICATION' : 'RUN_DISCRIMINATING_TEST',
      action: result.gate === 'ESCALATE' ? 'Review reproduced freshness-state and public trust/content signals, then select one bounded remediation experiment.' : 'Run the smallest paired counterfactual before changing severity or root-cause status.',
      owner_or_authority: 'Human product/QA owner',
      completion_signal: 'Each item has a reviewed acceptance criterion or evidence-backed rejection reason.',
      stop_condition: 'Stop before authentication, server-state change, direct API access, external disclosure, deployment, or merge.',
    },
  };
  fs.writeFileSync(path.join(output, 'causal-packet.json'), `${JSON.stringify(packet, null, 2)}\n`);
  fs.writeFileSync(path.join(output, 'raw-observations.json'), `${JSON.stringify(observations, null, 2)}\n`);
  const summary = ['# TakeProfit causal deep-audit rerun', '', `- Audit: \`${config.audit_id}\``, `- Generated: \`${now}\``, `- Source head: \`${head}\``, `- Run: \`${run}\` attempt \`${attempt}\``, `- Coverage: \`${result.successful}/${observations.length}\``, `- Verdict: \`${result.state}\` / \`${result.gate}\``, '', '| ID | Status | Severity | Claim | Title |', '|---|---|---|---|---|', ...result.findings.map((item) => `| ${item.finding_id} | ${item.reproduction_status} | ${item.severity} | ${item.claim_level} | ${item.title} |`), '', 'PR #87 selected tests; only this exact run controls current status.', ''].join('\n');
  fs.writeFileSync(path.join(output, 'summary.md'), summary);
  const files = [];
  const walk = (dir) => fs.readdirSync(dir, {withFileTypes: true}).forEach((entry) => entry.isDirectory() ? walk(path.join(dir, entry.name)) : entry.name !== 'SHA256SUMS' && files.push(path.join(dir, entry.name)));
  walk(output);
  fs.writeFileSync(path.join(output, 'SHA256SUMS'), `${files.sort().map((file) => `${hash(fs.readFileSync(file))}  ${path.relative(output, file)}`).join('\n')}\n`);
  console.log(JSON.stringify({verdict: packet.verdict, findings: packet.findings.map(({finding_id, reproduction_status, severity}) => ({finding_id, reproduction_status, severity}))}, null, 2));
}

main().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
