import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash('sha256').update(String(value)).digest('hex');
const hostOf = (value) => { try { return new URL(value).hostname.toLowerCase(); } catch { return null; } };
const cleanUrl = (value) => { try { const u = new URL(value); return `${u.protocol}//${u.host}${u.pathname}`; } catch { return '<invalid-url>'; } };

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) out[key] = true;
    else { out[key] = value; i += 1; }
  }
  for (const key of ['config', 'chrome', 'output-dir']) if (!out[key]) throw new Error(`missing --${key}`);
  return out;
}

function stableHash(value) {
  const sort = (item) => Array.isArray(item)
    ? item.map(sort)
    : item && typeof item === 'object'
      ? Object.fromEntries(Object.keys(item).sort().map((key) => [key, sort(item[key])]))
      : item;
  return sha256(JSON.stringify(sort(value)));
}

async function accessibilitySnapshot(client) {
  const tree = await client.send('Accessibility.getFullAXTree').catch(() => ({ nodes: [] }));
  const roles = {};
  let named = 0;
  let ignored = 0;
  for (const node of tree.nodes || []) {
    const role = node.role?.value || 'unknown';
    roles[role] = (roles[role] || 0) + 1;
    if (node.name?.value) named += 1;
    if (node.ignored) ignored += 1;
  }
  return {
    ax_node_count: (tree.nodes || []).length,
    ax_named_node_count: named,
    ax_ignored_node_count: ignored,
    ax_role_counts: roles
  };
}

async function capture(browser, config, label, blockTarget, outputDir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(config.profile.user_agent);
  await page.setViewport(config.profile.viewport);
  await page.setCacheEnabled(false);

  const client = await page.target().createCDPSession();
  await client.send('Network.enable');
  await client.send('Network.setCacheDisabled', { cacheDisabled: true });
  await client.send('Network.setBypassServiceWorker', { bypass: true });
  await client.send('Accessibility.enable');

  const network = {
    requests: 0,
    responses: 0,
    failed_requests: 0,
    script_requests: 0,
    target_host_script_requests: 0,
    blocked_target_host_script_requests: 0,
    status_counts: {},
    console_event_hashes: [],
    page_error_hashes: []
  };

  await page.setRequestInterception(true);
  page.on('request', (request) => {
    network.requests += 1;
    const host = hostOf(request.url());
    if (request.resourceType() === 'script') {
      network.script_requests += 1;
      if (host === config.blocked_host) {
        network.target_host_script_requests += 1;
        if (blockTarget) {
          network.blocked_target_host_script_requests += 1;
          request.abort('blockedbyclient');
          return;
        }
      }
    }
    request.continue();
  });
  page.on('response', (response) => {
    network.responses += 1;
    const key = String(response.status());
    network.status_counts[key] = (network.status_counts[key] || 0) + 1;
  });
  page.on('requestfailed', () => { network.failed_requests += 1; });
  page.on('console', (message) => {
    if (network.console_event_hashes.length >= 40) return;
    const text = message.text();
    network.console_event_hashes.push({ type: message.type(), sha256: sha256(text), length: text.length });
  });
  page.on('pageerror', (error) => {
    if (network.page_error_hashes.length >= 20) return;
    const text = String(error?.message || error);
    network.page_error_hashes.push({ sha256: sha256(text), length: text.length });
  });

  let navigationStatus = null;
  try {
    const response = await page.goto(config.target.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    navigationStatus = response?.status() ?? null;
    await sleep(config.timings_ms.settle_after_domcontentloaded);
  } catch (error) {
    const text = String(error?.message || error);
    network.page_error_hashes.push({ sha256: sha256(text), length: text.length });
  }

  const state = await page.evaluate((terms) => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
    };
    const text = document.body?.innerText || '';
    const lower = text.toLowerCase();
    const identityHaystack = `${document.title || ''} ${text}`.toLowerCase();
    const matched = terms.filter((term) => identityHaystack.includes(term.toLowerCase()));
    return {
      final_url: `${location.protocol}//${location.host}${location.pathname}`,
      title: document.title || '',
      raw_text: text,
      body_child_count: document.body?.children.length || 0,
      main_landmarks: document.querySelectorAll('main,[role="main"]').length,
      navigation_landmarks: document.querySelectorAll('nav,[role="navigation"]').length,
      visible_links: [...document.querySelectorAll('a[href]')].filter(visible).length,
      visible_buttons: [...document.querySelectorAll('button,[role="button"]')].filter(visible).length,
      visible_inputs: [...document.querySelectorAll('input,select,textarea,[role="searchbox"]')].filter(visible).length,
      route_identity_match: matched.length > 0,
      matched_expected_terms: matched,
      generic_app_error_visible: ['whoops, something went wrong', "the app had an error it couldn't recover from", 'something went wrong'].some((term) => lower.includes(term)),
      recovery_guidance_visible: ['refresh', 'reload', 'try again'].some((term) => lower.includes(term)),
      html_lang: document.documentElement.lang || null
    };
  }, config.target.expected_terms).catch(() => ({
    final_url: cleanUrl(page.url()), title: '', raw_text: '', body_child_count: 0,
    main_landmarks: 0, navigation_landmarks: 0, visible_links: 0,
    visible_buttons: 0, visible_inputs: 0, route_identity_match: false,
    matched_expected_terms: [], generic_app_error_visible: false,
    recovery_guidance_visible: false, html_lang: null
  }));

  const rawText = state.raw_text || '';
  delete state.raw_text;
  Object.assign(state, {
    label,
    blocked_host: blockTarget ? config.blocked_host : null,
    requested_url: cleanUrl(config.target.url),
    navigation_status: navigationStatus,
    text_length: rawText.length,
    text_sha256: sha256(rawText),
    captured_at_utc: new Date().toISOString()
  }, await accessibilitySnapshot(client));

  fs.mkdirSync(outputDir, { recursive: true });
  const screenshotPath = path.join(outputDir, `${label}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
  state.screenshot_sha256 = fs.existsSync(screenshotPath) ? sha256(fs.readFileSync(screenshotPath)) : null;

  await page.close().catch(() => {});
  await context.close().catch(() => {});
  return { state, network };
}

const meaningful = (result, config) => result.state.route_identity_match
  && result.state.main_landmarks >= config.thresholds.meaningful_main_landmarks
  && result.state.visible_inputs >= config.thresholds.meaningful_visible_inputs
  && !result.state.generic_app_error_visible;

function classify(rounds, config) {
  const count = (predicate) => rounds.filter(predicate).length;
  const required = config.thresholds.required_rounds;
  const result = {
    host: config.blocked_host,
    rounds: rounds.length,
    baseline_host_observed: count((round) => round.baseline.network.target_host_script_requests > 0),
    baseline_meaningful: count((round) => meaningful(round.baseline, config)),
    treatment_host_blocked: count((round) => round.treatment.network.blocked_target_host_script_requests > 0),
    treatment_generic_error: count((round) => round.treatment.state.generic_app_error_visible),
    treatment_route_identity_lost: count((round) => !round.treatment.state.route_identity_match),
    treatment_meaningful: count((round) => meaningful(round.treatment, config)),
    recovery_meaningful: count((round) => meaningful(round.recovery, config)),
    verdict: 'NEEDS_EVIDENCE'
  };

  const common = result.baseline_host_observed === required
    && result.baseline_meaningful === required
    && result.treatment_host_blocked === required
    && result.recovery_meaningful === required;

  if (common && result.treatment_generic_error === required && result.treatment_route_identity_lost === required) {
    result.verdict = 'SUPPORTED_HOST_DEPENDENCY';
  } else if (common && result.treatment_meaningful === required && result.treatment_generic_error === 0) {
    result.verdict = 'NEUTRAL_UNDER_BOUNDED_TEST';
  }
  return result;
}

function summary(result) {
  const c = result.classification;
  return [
    '# Starbucks mobile Store Locator xg4ken control',
    '',
    `Host: ${c.host}`,
    `Rounds: ${c.rounds}`,
    `Navigations: ${result.total_navigations}`,
    '',
    '| Baseline host observed | Baseline meaningful | Host blocked | Generic error | Identity lost | Treatment meaningful | Recovery meaningful | Verdict |',
    '|---:|---:|---:|---:|---:|---:|---:|---|',
    `| ${c.baseline_host_observed}/${c.rounds} | ${c.baseline_meaningful}/${c.rounds} | ${c.treatment_host_blocked}/${c.rounds} | ${c.treatment_generic_error}/${c.rounds} | ${c.treatment_route_identity_lost}/${c.rounds} | ${c.treatment_meaningful}/${c.rounds} | ${c.recovery_meaningful}/${c.rounds} | ${c.verdict} |`,
    '',
    '## Boundary',
    '',
    '- This experiment blocks one exact script host only.',
    '- A neutral result applies only to this bounded mobile Store Locator scenario.',
    '- A supported dependency does not prove provider fault.',
    '- Bodies, headers, cookies, storage, form values, console text, and page-error text are not retained.',
    ''
  ].join('\n');
}

async function main() {
  const argv = parseArgs(process.argv);
  const config = JSON.parse(fs.readFileSync(argv.config, 'utf8'));
  const outputDir = path.resolve(argv['output-dir']);
  fs.mkdirSync(outputDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: argv.chrome,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking']
  });

  try {
    const rounds = [];
    for (let round = 1; round <= config.rounds; round += 1) {
      const roundDir = path.join(outputDir, `round-${round}`);
      const baseline = await capture(browser, config, 'baseline', false, roundDir);
      const treatment = await capture(browser, config, 'host_blocked', true, roundDir);
      const recovery = await capture(browser, config, 'recovery', false, roundDir);
      const record = { round, baseline, treatment, recovery };
      rounds.push(record);
      fs.writeFileSync(path.join(roundDir, 'pair.json'), `${JSON.stringify(record, null, 2)}\n`);
    }

    const result = {
      schema_version: 'liminalqa-starbucks-store-locator-xg4ken-control-result-v0.1',
      observed_at_utc: new Date().toISOString(),
      config_sha256: stableHash(config),
      target: config.target,
      profile: config.profile.id,
      blocked_host: config.blocked_host,
      rounds,
      classification: classify(rounds, config),
      total_navigations: config.rounds * 3,
      boundaries: config.boundaries,
      authority: config.authority
    };
    result.result_sha256 = stableHash(result);
    fs.writeFileSync(path.join(outputDir, 'aggregate.json'), `${JSON.stringify(result, null, 2)}\n`);
    fs.writeFileSync(path.join(outputDir, 'summary.md'), summary(result));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
