import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

function parseArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) {
      args[key] = true;
    } else {
      args[key] = value;
      index += 1;
    }
  }
  for (const key of ['config', 'chrome', 'output-dir']) {
    if (!args[key]) throw new Error(`missing --${key}`);
  }
  return args;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash('sha256').update(String(value)).digest('hex');

function normalizeUrl(raw) {
  try {
    const url = new URL(raw);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch {
    return '<invalid-url>';
  }
}

function hostname(raw) {
  try {
    return new URL(raw).hostname.toLowerCase();
  } catch {
    return '';
  }
}

function isStarbucksHost(raw) {
  const host = hostname(raw);
  return host === 'starbucks.com' || host.endsWith('.starbucks.com');
}

function freshPhaseStats() {
  return {
    requests: 0,
    responses: 0,
    failed_requests: 0,
    first_party_requests: 0,
    third_party_requests: 0,
    script_requests: 0,
    first_party_script_requests: 0,
    third_party_script_requests: 0,
    blocked_first_party_scripts: 0,
    blocked_third_party_scripts: 0,
    status_counts: {},
    normalized_first_party_scripts: {},
    console_event_hashes: [],
    page_error_hashes: []
  };
}

function increment(map, key) {
  map[key] = (map[key] || 0) + 1;
}

function semanticState(snapshot, thresholds) {
  return {
    meaningful: snapshot.text_length >= thresholds.minimum_meaningful_text_chars && snapshot.main_landmarks >= 1,
    route_identity: snapshot.route_identity_match,
    terminal_js_message: snapshot.javascript_required_visible,
    accessible_structure: snapshot.ax_node_count >= thresholds.minimum_ax_nodes && snapshot.main_landmarks >= 1
  };
}

function classifyPair(pair, config) {
  const baseline = semanticState(pair.phases.baseline.snapshot, config.thresholds);
  const thirdParty = semanticState(pair.phases.third_party_scripts_blocked.snapshot, config.thresholds);
  const firstParty = semanticState(pair.phases.first_party_scripts_blocked.snapshot, config.thresholds);
  const recovery = semanticState(pair.phases.recovery.snapshot, config.thresholds);

  const firstPartyBlocked = pair.phases.first_party_scripts_blocked.network.blocked_first_party_scripts > 0;
  const thirdPartyBlocked = pair.phases.third_party_scripts_blocked.network.blocked_third_party_scripts > 0;
  const baselineValid = baseline.meaningful && baseline.route_identity && !baseline.terminal_js_message;
  const thirdPartyControlValid = thirdPartyBlocked && thirdParty.meaningful && thirdParty.route_identity && !thirdParty.terminal_js_message;
  const firstPartyTerminal = firstPartyBlocked && (
    firstParty.terminal_js_message ||
    !firstParty.meaningful ||
    !firstParty.route_identity ||
    !firstParty.accessible_structure
  );
  const recoveryRestored = recovery.meaningful && recovery.route_identity && !recovery.terminal_js_message;

  return {
    baseline_valid: baselineValid,
    third_party_control_valid: thirdPartyControlValid,
    first_party_terminal_state: firstPartyTerminal,
    recovery_restored: recoveryRestored,
    first_party_script_block_observed: firstPartyBlocked,
    third_party_script_block_observed: thirdPartyBlocked
  };
}

function aggregateCell(target, profile, pairs, config) {
  const counts = {
    rounds: pairs.length,
    baseline_valid: 0,
    third_party_control_valid: 0,
    first_party_terminal_state: 0,
    recovery_restored: 0,
    first_party_script_block_observed: 0,
    third_party_script_block_observed: 0
  };
  for (const pair of pairs) {
    for (const key of Object.keys(counts)) {
      if (key === 'rounds') continue;
      if (pair.classification[key]) counts[key] += 1;
    }
  }

  const findings = [];
  const candidates = [];
  const diagnostics = [];
  const required = config.rounds;

  if (
    counts.baseline_valid === required &&
    counts.third_party_control_valid === required &&
    counts.first_party_terminal_state === required &&
    counts.recovery_restored === required
  ) {
    findings.push({
      id: 'first-party-javascript-terminal-state-reproduced',
      verdict: 'SUPPORTED',
      severity_candidate: 'P2',
      evidence: `${required}/${required} fresh contexts retained route identity with third-party scripts blocked, entered a terminal or structurally empty state when first-party scripts were blocked, and recovered after scripts were restored.`
    });
  } else {
    if (counts.baseline_valid < required) {
      candidates.push({
        id: 'baseline-instability',
        verdict: 'NEEDS_EVIDENCE',
        evidence: `${counts.baseline_valid}/${required} baseline runs met the route identity and meaningful-content contract.`
      });
    }
    if (counts.first_party_script_block_observed < required) {
      candidates.push({
        id: 'first-party-block-not-proven',
        verdict: 'NEEDS_EVIDENCE',
        evidence: `${counts.first_party_script_block_observed}/${required} runs actually blocked at least one first-party script request.`
      });
    }
    if (counts.third_party_script_block_observed < required) {
      diagnostics.push({
        id: 'no-third-party-script-control',
        verdict: 'NOT_TESTABLE',
        evidence: `${counts.third_party_script_block_observed}/${required} runs observed at least one blockable third-party script request.`
      });
    }
    if (counts.first_party_terminal_state > 0 && counts.first_party_terminal_state < required) {
      candidates.push({
        id: 'intermittent-first-party-javascript-terminal-state',
        verdict: 'NEEDS_EVIDENCE',
        evidence: `${counts.first_party_terminal_state}/${required} runs entered a terminal or structurally empty state under first-party script blocking.`
      });
    }
    if (counts.recovery_restored < required) {
      candidates.push({
        id: 'recovery-not-consistently-restored',
        verdict: 'NEEDS_EVIDENCE',
        evidence: `${counts.recovery_restored}/${required} runs restored meaningful route identity after first-party scripts were re-enabled.`
      });
    }
    if (counts.third_party_control_valid < required && counts.first_party_terminal_state > 0) {
      candidates.push({
        id: 'first-party-isolation-confounded',
        verdict: 'NEEDS_EVIDENCE',
        evidence: `Third-party script blocking retained meaningful route behavior in ${counts.third_party_control_valid}/${required} runs, so first-party-specific causality is not fully isolated.`
      });
    }
  }

  if (!findings.length && !candidates.length) {
    diagnostics.push({
      id: 'no-terminal-state-reproduced',
      verdict: 'PASS',
      evidence: 'No deterministic first-party JavaScript terminal state crossed the configured multi-round threshold.'
    });
  }

  return {
    target_id: target.id,
    profile_id: profile.id,
    counts,
    findings,
    candidates,
    diagnostics
  };
}

async function captureAccessibility(client) {
  const tree = await client.send('Accessibility.getFullAXTree').catch(() => ({ nodes: [] }));
  const roleCounts = {};
  let namedNodes = 0;
  let ignoredNodes = 0;
  for (const node of tree.nodes || []) {
    const role = node.role?.value || 'unknown';
    increment(roleCounts, role);
    if (node.name?.value) namedNodes += 1;
    if (node.ignored) ignoredNodes += 1;
  }
  return {
    ax_node_count: (tree.nodes || []).length,
    ax_named_node_count: namedNodes,
    ax_ignored_node_count: ignoredNodes,
    ax_role_counts: roleCounts
  };
}

async function captureSnapshot(page, client, target, phase, phaseStats, screenshotPath) {
  const dom = await page.evaluate((expectedTerms) => {
    const body = document.body;
    const text = (body?.innerText || '').replace(/\s+/g, ' ').trim();
    const lower = text.toLowerCase();
    const visible = (element) => {
      if (!(element instanceof Element)) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
    };
    const mainLandmarks = [...document.querySelectorAll('main, [role="main"]')].filter(visible);
    const navLandmarks = [...document.querySelectorAll('nav, [role="navigation"]')].filter(visible);
    const jsPhrases = [
      'this site requires javascript',
      'requires javascript',
      'enable javascript',
      'javascript is required'
    ];
    const recoveryPhrases = ['try again', 'retry', 'refresh', 'support', 'help'];
    const matchedTerms = expectedTerms.filter((term) => lower.includes(term.toLowerCase()));
    return {
      final_url: location.href,
      title: document.title,
      text_length: text.length,
      text_sha256_input: text,
      body_child_count: body?.children.length || 0,
      main_landmarks: mainLandmarks.length,
      navigation_landmarks: navLandmarks.length,
      visible_links: [...document.querySelectorAll('a[href]')].filter(visible).length,
      visible_buttons: [...document.querySelectorAll('button, [role="button"]')].filter(visible).length,
      visible_inputs: [...document.querySelectorAll('input, select, textarea')].filter(visible).length,
      route_identity_match: matchedTerms.length > 0,
      matched_expected_terms: matchedTerms,
      javascript_required_visible: jsPhrases.some((phrase) => lower.includes(phrase)),
      recovery_guidance_visible: recoveryPhrases.some((phrase) => lower.includes(phrase)),
      html_lang: document.documentElement.lang || null
    };
  }, target.expected_terms).catch(() => ({
    final_url: page.url(),
    title: '',
    text_length: 0,
    text_sha256_input: '',
    body_child_count: 0,
    main_landmarks: 0,
    navigation_landmarks: 0,
    visible_links: 0,
    visible_buttons: 0,
    visible_inputs: 0,
    route_identity_match: false,
    matched_expected_terms: [],
    javascript_required_visible: false,
    recovery_guidance_visible: false,
    html_lang: null
  }));

  const textHash = sha256(dom.text_sha256_input);
  delete dom.text_sha256_input;
  const accessibility = await captureAccessibility(client);
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
  const screenshotHash = fs.existsSync(screenshotPath) ? sha256(fs.readFileSync(screenshotPath)) : null;

  return {
    phase,
    captured_at_utc: new Date().toISOString(),
    requested_url: target.url,
    final_url: normalizeUrl(dom.final_url),
    navigation_status: phaseStats.navigation_status,
    text_sha256: textHash,
    screenshot_sha256: screenshotHash,
    ...dom,
    ...accessibility
  };
}

async function navigateAndCapture(page, client, target, phase, stats, config, outputDir) {
  stats.navigation_status = null;
  const response = await page.goto(target.url, {
    waitUntil: 'domcontentloaded',
    timeout: config.timings_ms.navigation_timeout
  }).catch(() => null);
  stats.navigation_status = response?.status() ?? null;
  await sleep(config.timings_ms.settle);
  const screenshotPath = path.join(outputDir, `${phase}.png`);
  const snapshot = await captureSnapshot(page, client, target, phase, stats, screenshotPath);
  await page.evaluate(() => window.stop()).catch(() => {});
  await sleep(config.timings_ms.between_navigations);
  return { snapshot, network: stats };
}

async function runPair(browser, config, target, profile, round, outputRoot) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.setBypassServiceWorker(true);
  const client = await page.target().createCDPSession();
  await client.send('Network.enable');
  await client.send('Network.setCacheDisabled', { cacheDisabled: true });
  await client.send('Accessibility.enable');
  await client.send('Emulation.setCPUThrottlingRate', { rate: profile.cpu_throttling_rate });

  let phase = 'baseline';
  const phaseStats = {
    baseline: freshPhaseStats(),
    third_party_scripts_blocked: freshPhaseStats(),
    first_party_scripts_blocked: freshPhaseStats(),
    recovery: freshPhaseStats()
  };

  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const stats = phaseStats[phase];
    const url = request.url();
    const resourceType = request.resourceType();
    const firstParty = isStarbucksHost(url);
    stats.requests += 1;
    stats[firstParty ? 'first_party_requests' : 'third_party_requests'] += 1;
    if (resourceType === 'script') {
      stats.script_requests += 1;
      if (firstParty) {
        stats.first_party_script_requests += 1;
        const normalized = normalizeUrl(url);
        stats.normalized_first_party_scripts[normalized] = (stats.normalized_first_party_scripts[normalized] || 0) + 1;
      } else {
        stats.third_party_script_requests += 1;
      }
    }

    const blockFirstParty = phase === 'first_party_scripts_blocked' && resourceType === 'script' && firstParty;
    const blockThirdParty = phase === 'third_party_scripts_blocked' && resourceType === 'script' && !firstParty;
    if (blockFirstParty) {
      stats.blocked_first_party_scripts += 1;
      request.abort('blockedbyclient');
      return;
    }
    if (blockThirdParty) {
      stats.blocked_third_party_scripts += 1;
      request.abort('blockedbyclient');
      return;
    }
    request.continue();
  });

  page.on('response', (response) => {
    const stats = phaseStats[phase];
    stats.responses += 1;
    increment(stats.status_counts, String(response.status()));
  });
  page.on('requestfailed', () => {
    phaseStats[phase].failed_requests += 1;
  });
  page.on('console', (message) => {
    const stats = phaseStats[phase];
    if (stats.console_event_hashes.length >= 30) return;
    const text = message.text().replace(/https?:\/\/[^\s]+/g, (value) => normalizeUrl(value)).slice(0, 1000);
    stats.console_event_hashes.push({ type: message.type(), sha256: sha256(text), length: text.length });
  });
  page.on('pageerror', (error) => {
    const stats = phaseStats[phase];
    if (stats.page_error_hashes.length >= 20) return;
    const text = String(error?.message || error).slice(0, 1000);
    stats.page_error_hashes.push({ sha256: sha256(text), length: text.length });
  });

  const pairDir = path.join(outputRoot, target.id, profile.id, `round-${round}`);
  fs.mkdirSync(pairDir, { recursive: true });
  const phases = {};
  try {
    phase = 'baseline';
    phases.baseline = await navigateAndCapture(page, client, target, phase, phaseStats[phase], config, pairDir);

    phase = 'third_party_scripts_blocked';
    phases.third_party_scripts_blocked = await navigateAndCapture(page, client, target, phase, phaseStats[phase], config, pairDir);

    phase = 'first_party_scripts_blocked';
    phases.first_party_scripts_blocked = await navigateAndCapture(page, client, target, phase, phaseStats[phase], config, pairDir);

    phase = 'recovery';
    phases.recovery = await navigateAndCapture(page, client, target, phase, phaseStats[phase], config, pairDir);
  } finally {
    await context.close();
  }

  for (const item of Object.values(phases)) {
    delete item.network.navigation_status;
    item.network.normalized_first_party_scripts = Object.fromEntries(
      Object.entries(item.network.normalized_first_party_scripts)
        .sort(([left], [right]) => left.localeCompare(right))
        .slice(0, config.boundaries.maximum_normalized_script_urls_per_phase)
    );
  }

  const pair = {
    schema_version: 'liminalqa-starbucks-route-resilience-pair-v0.1',
    target_id: target.id,
    profile_id: profile.id,
    round,
    phases
  };
  pair.classification = classifyPair(pair, config);
  fs.writeFileSync(path.join(pairDir, 'pair.json'), `${JSON.stringify(pair, null, 2)}\n`);
  return pair;
}

function buildSummary(result) {
  const lines = [
    '# Starbucks public route resilience matrix',
    '',
    `Exact experiment cells: ${result.cells.length}`,
    `Fresh browser contexts: ${result.pairs.length}`,
    `Navigations: ${result.total_navigations}`,
    '',
    '| Route | Profile | Baseline | Third-party control | First-party terminal | Recovery | Verdict |',
    '|---|---|---:|---:|---:|---:|---|'
  ];
  for (const cell of result.cells) {
    const verdict = cell.findings.length ? 'SUPPORTED_FINDING' : cell.candidates.length ? 'NEEDS_EVIDENCE' : 'PASS';
    lines.push(`| ${cell.target_id} | ${cell.profile_id} | ${cell.counts.baseline_valid}/${cell.counts.rounds} | ${cell.counts.third_party_control_valid}/${cell.counts.rounds} | ${cell.counts.first_party_terminal_state}/${cell.counts.rounds} | ${cell.counts.recovery_restored}/${cell.counts.rounds} | ${verdict} |`);
  }
  lines.push('', '## Evidence boundary', '');
  lines.push('- Browser navigation only; no direct application API calls.');
  lines.push('- One page at a time; all contexts run sequentially.');
  lines.push('- Request and response bodies, headers, cookies, storage, and form values are not retained.');
  lines.push('- First-party JavaScript causality is supported only when the third-party-block control remains meaningful in every round.');
  lines.push('- A JavaScript terminal state is not automatically classified as a WCAG violation.');
  return `${lines.join('\n')}\n`;
}

async function main() {
  const args = parseArgs(process.argv);
  const config = JSON.parse(fs.readFileSync(args.config, 'utf8'));
  const outputRoot = path.resolve(args['output-dir']);
  fs.mkdirSync(outputRoot, { recursive: true });

  const expectedNavigations = config.targets.length * config.profiles.length * config.rounds * 4;
  if (expectedNavigations > config.boundaries.maximum_total_navigations) {
    throw new Error(`planned ${expectedNavigations} navigations exceeds boundary ${config.boundaries.maximum_total_navigations}`);
  }

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });

  const pairs = [];
  try {
    for (const target of config.targets) {
      for (const profile of config.profiles) {
        for (let round = 1; round <= config.rounds; round += 1) {
          pairs.push(await runPair(browser, config, target, profile, round, outputRoot));
        }
      }
    }
  } finally {
    await browser.close();
  }

  const cells = [];
  for (const target of config.targets) {
    for (const profile of config.profiles) {
      const cellPairs = pairs.filter((pair) => pair.target_id === target.id && pair.profile_id === profile.id);
      cells.push(aggregateCell(target, profile, cellPairs, config));
    }
  }

  const result = {
    schema_version: 'liminalqa-starbucks-route-resilience-result-v0.1',
    observed_at_utc: new Date().toISOString(),
    config_sha256: sha256(fs.readFileSync(args.config)),
    total_navigations: expectedNavigations,
    pairs,
    cells,
    authority: config.authority,
    boundaries: config.boundaries
  };
  result.result_sha256 = sha256(JSON.stringify(result));
  fs.writeFileSync(path.join(outputRoot, 'aggregate.json'), `${JSON.stringify(result, null, 2)}\n`);
  fs.writeFileSync(path.join(outputRoot, 'summary.md'), buildSummary(result));
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
