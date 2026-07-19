import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const hash = (v) => crypto.createHash('sha256').update(v).digest('hex');
const inc = (o, k) => { o[k] = (o[k] || 0) + 1; };
const hostOf = (u) => { try { return new URL(u).hostname.toLowerCase(); } catch { return null; } };
const firstParty = (h) => h === 'starbucks.com' || h?.endsWith('.starbucks.com');
const cleanUrl = (u) => { try { const x = new URL(u); return `${x.protocol}//${x.host}${x.pathname}`; } catch { return '<invalid-url>'; } };

function args(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue;
    const k = argv[i].slice(2), v = argv[i + 1];
    if (!v || v.startsWith('--')) out[k] = true;
    else { out[k] = v; i += 1; }
  }
  for (const k of ['config', 'chrome', 'output-dir']) if (!out[k]) throw new Error(`missing --${k}`);
  return out;
}

function stableHash(value) {
  const sort = (v) => Array.isArray(v) ? v.map(sort) : v && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sort(v[k])])) : v;
  return hash(JSON.stringify(sort(value)));
}

async function ax(client) {
  const tree = await client.send('Accessibility.getFullAXTree').catch(() => ({ nodes: [] }));
  const roles = {}; let named = 0; let ignored = 0;
  for (const n of tree.nodes || []) {
    inc(roles, n.role?.value || 'unknown');
    if (n.name?.value) named += 1;
    if (n.ignored) ignored += 1;
  }
  return { ax_node_count: (tree.nodes || []).length, ax_named_node_count: named, ax_ignored_node_count: ignored, ax_role_counts: roles };
}

async function navigate(browser, cfg, label, blockedHost, dir) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(cfg.profile.user_agent);
  await page.setViewport(cfg.profile.viewport);
  await page.setCacheEnabled(false);
  const client = await page.target().createCDPSession();
  await client.send('Network.enable');
  await client.send('Network.setCacheDisabled', { cacheDisabled: true });
  await client.send('Network.setBypassServiceWorker', { bypass: true });
  await client.send('Accessibility.enable');

  const net = { requests: 0, responses: 0, failed_requests: 0, script_requests: 0, third_party_script_requests: 0, blocked_script_requests: 0, status_counts: {}, third_party_script_hosts: {}, console_event_hashes: [], page_error_hashes: [] };
  await page.setRequestInterception(true);
  page.on('request', (r) => {
    net.requests += 1;
    const h = hostOf(r.url());
    if (r.resourceType() === 'script') {
      net.script_requests += 1;
      if (h && !firstParty(h)) { net.third_party_script_requests += 1; inc(net.third_party_script_hosts, h); }
      if (blockedHost && h === blockedHost) { net.blocked_script_requests += 1; r.abort('blockedbyclient'); return; }
    }
    r.continue();
  });
  page.on('response', (r) => { net.responses += 1; inc(net.status_counts, String(r.status())); });
  page.on('requestfailed', () => { net.failed_requests += 1; });
  page.on('console', (m) => { if (net.console_event_hashes.length < 40) { const t = m.text(); net.console_event_hashes.push({ type: m.type(), sha256: hash(t), length: t.length }); } });
  page.on('pageerror', (e) => { if (net.page_error_hashes.length < 20) { const t = String(e?.message || e); net.page_error_hashes.push({ sha256: hash(t), length: t.length }); } });

  let status = null;
  try {
    const r = await page.goto(cfg.target.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    status = r?.status() ?? null;
    await sleep(cfg.timings_ms.settle_after_domcontentloaded);
  } catch (e) {
    const t = String(e?.message || e); net.page_error_hashes.push({ sha256: hash(t), length: t.length });
  }

  const state = await page.evaluate((terms) => {
    const visible = (e) => { const s = getComputedStyle(e), r = e.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) > 0 && r.width > 0 && r.height > 0; };
    const text = document.body?.innerText || '', low = text.toLowerCase();
    const hay = `${location.pathname} ${document.title} ${text}`.toLowerCase();
    const matched = terms.filter((t) => hay.includes(t.toLowerCase()));
    return {
      final_url: `${location.protocol}//${location.host}${location.pathname}`,
      title: document.title || '', raw_text: text, body_child_count: document.body?.children.length || 0,
      main_landmarks: document.querySelectorAll('main,[role="main"]').length,
      navigation_landmarks: document.querySelectorAll('nav,[role="navigation"]').length,
      visible_links: [...document.querySelectorAll('a[href]')].filter(visible).length,
      visible_buttons: [...document.querySelectorAll('button,[role="button"]')].filter(visible).length,
      visible_inputs: [...document.querySelectorAll('input,select,textarea,[role="searchbox"]')].filter(visible).length,
      route_identity_match: matched.length > 0, matched_expected_terms: matched,
      generic_app_error_visible: ['whoops, something went wrong', "the app had an error it couldn't recover from", 'something went wrong'].some((t) => low.includes(t)),
      recovery_guidance_visible: ['refresh', 'reload', 'try again'].some((t) => low.includes(t)),
      html_lang: document.documentElement.lang || null
    };
  }, cfg.target.expected_terms).catch(() => ({ final_url: cleanUrl(page.url()), title: '', raw_text: '', body_child_count: 0, main_landmarks: 0, navigation_landmarks: 0, visible_links: 0, visible_buttons: 0, visible_inputs: 0, route_identity_match: false, matched_expected_terms: [], generic_app_error_visible: false, recovery_guidance_visible: false, html_lang: null }));

  const raw = state.raw_text || ''; delete state.raw_text;
  Object.assign(state, { label, blocked_host: blockedHost || null, requested_url: cleanUrl(cfg.target.url), navigation_status: status, text_length: raw.length, text_sha256: hash(raw), captured_at_utc: new Date().toISOString() }, await ax(client));
  fs.mkdirSync(dir, { recursive: true });
  const shot = path.join(dir, `${label}.png`);
  await page.screenshot({ path: shot, fullPage: true }).catch(() => {});
  state.screenshot_sha256 = fs.existsSync(shot) ? hash(fs.readFileSync(shot)) : null;
  await page.close().catch(() => {}); await context.close().catch(() => {});
  return { state, network: net };
}

const meaningful = (r, c) => r.state.route_identity_match && r.state.main_landmarks >= c.thresholds.meaningful_main_landmarks && r.state.visible_inputs >= c.thresholds.meaningful_visible_inputs && !r.state.generic_app_error_visible;

function classify(host, rounds, c) {
  const count = (f) => rounds.filter(f).length, required = c.isolation_rounds;
  const cell = {
    host, rounds: rounds.length,
    baseline_meaningful: count((x) => meaningful(x.baseline, c)),
    treatment_blocked: count((x) => x.treatment.network.blocked_script_requests > 0),
    treatment_generic_error: count((x) => x.treatment.state.generic_app_error_visible),
    treatment_route_identity_lost: count((x) => !x.treatment.state.route_identity_match),
    treatment_meaningful: count((x) => meaningful(x.treatment, c)),
    recovery_meaningful: count((x) => meaningful(x.recovery, c)),
    verdict: 'NEEDS_EVIDENCE'
  };
  if (cell.baseline_meaningful === required && cell.treatment_blocked === required && cell.treatment_generic_error === c.thresholds.supported_failure_rounds && cell.treatment_route_identity_lost === required && cell.recovery_meaningful === required) cell.verdict = 'SUPPORTED_HOST_DEPENDENCY';
  else if (cell.baseline_meaningful === required && cell.treatment_blocked === required && cell.treatment_meaningful === c.thresholds.neutral_rounds && cell.treatment_generic_error === 0 && cell.recovery_meaningful === required) cell.verdict = 'NEUTRAL_UNDER_BOUNDED_TEST';
  return cell;
}

function summary(r) {
  const lines = ['# Starbucks mobile Store Locator third-party host isolation', '', `Inventory rounds: ${r.inventory.rounds.length}`, `Stable candidate hosts: ${r.inventory.candidate_hosts.length}`, `Navigations: ${r.total_navigations}`, '', '| Host | Presence | Blocked | Error | Identity lost | Recovery | Verdict |', '|---|---:|---:|---:|---:|---:|---|'];
  for (const c of r.cells) lines.push(`| ${c.host} | ${r.inventory.host_presence_rounds[c.host] || 0}/${r.inventory.rounds.length} | ${c.treatment_blocked}/${c.rounds} | ${c.treatment_generic_error}/${c.rounds} | ${c.treatment_route_identity_lost}/${c.rounds} | ${c.recovery_meaningful}/${c.rounds} | ${c.verdict} |`);
  lines.push('', '## Boundary', '', '- Supported requires the same generic error in 3/3 fresh contexts when one exact host is blocked, plus 3/3 recovery.', '- Host dependency does not prove provider fault; Starbucks integration or error containment may remain causal.', '- Bodies, headers, cookies, storage, form values, console text, and page-error text are not retained.');
  return `${lines.join('\n')}\n`;
}

async function main() {
  const a = args(process.argv), cfg = JSON.parse(fs.readFileSync(a.config, 'utf8')), out = path.resolve(a['output-dir']);
  fs.mkdirSync(out, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: a.chrome, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking'] });
  try {
    const inv = [];
    for (let round = 1; round <= cfg.inventory_rounds; round += 1) {
      const dir = path.join(out, 'inventory', `round-${round}`), result = await navigate(browser, cfg, 'baseline', null, dir);
      inv.push({ round, result }); fs.writeFileSync(path.join(dir, 'inventory.json'), `${JSON.stringify({ round, result }, null, 2)}\n`);
    }
    const presence = {}, counts = {};
    for (const x of inv) for (const [h, n] of Object.entries(x.result.network.third_party_script_hosts)) { inc(presence, h); counts[h] = (counts[h] || 0) + n; }
    const hosts = Object.keys(presence).filter((h) => presence[h] >= cfg.minimum_inventory_presence_rounds).sort((a, b) => presence[b] - presence[a] || counts[b] - counts[a] || a.localeCompare(b)).slice(0, cfg.max_candidate_hosts);
    const cells = [], details = [];
    for (const host of hosts) {
      const rounds = [], hdir = host.replace(/[^a-z0-9.-]/gi, '_');
      for (let round = 1; round <= cfg.isolation_rounds; round += 1) {
        const dir = path.join(out, 'hosts', hdir, `round-${round}`);
        const baseline = await navigate(browser, cfg, 'baseline', null, dir);
        const treatment = await navigate(browser, cfg, 'host_blocked', host, dir);
        const recovery = await navigate(browser, cfg, 'recovery', null, dir);
        const pair = { host, round, baseline, treatment, recovery }; rounds.push(pair); fs.writeFileSync(path.join(dir, 'pair.json'), `${JSON.stringify(pair, null, 2)}\n`);
      }
      const cell = classify(host, rounds, cfg); cells.push(cell); details.push({ host, rounds, classification: cell });
    }
    const result = { schema_version: 'liminalqa-starbucks-store-locator-host-isolation-result-v0.1', observed_at_utc: new Date().toISOString(), config_sha256: stableHash(cfg), target: cfg.target, profile: cfg.profile.id, inventory: { rounds: inv, host_presence_rounds: presence, host_script_request_counts: counts, candidate_hosts: hosts }, cells, cell_details: details, total_navigations: cfg.inventory_rounds + hosts.length * cfg.isolation_rounds * 3, boundaries: cfg.boundaries, authority: cfg.authority };
    result.result_sha256 = stableHash(result);
    fs.writeFileSync(path.join(out, 'aggregate.json'), `${JSON.stringify(result, null, 2)}\n`); fs.writeFileSync(path.join(out, 'summary.md'), summary(result));
  } finally { await browser.close(); }
}

main().catch((e) => { console.error(e?.stack || e); process.exitCode = 1; });
