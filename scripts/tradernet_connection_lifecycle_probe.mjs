import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) {
      args[key] = true;
    } else {
      args[key] = value;
      i += 1;
    }
  }
  for (const required of ['config', 'chrome', 'output-dir']) {
    if (!args[required]) throw new Error(`missing --${required}`);
  }
  return args;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (text) => crypto.createHash('sha256').update(String(text)).digest('hex');

function safeUrl(raw) {
  try {
    const url = new URL(raw);
    return `${url.protocol}//${url.host}${url.pathname}`;
  } catch {
    return '<invalid-url>';
  }
}

function isTradernet(raw) {
  try {
    const host = new URL(raw).hostname.toLowerCase();
    return host === 'tradernet.ru' || host.endsWith('.tradernet.ru');
  } catch {
    return false;
  }
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function round(value, digits = 1) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function phaseCounter() {
  return {
    bootstrap: 0,
    offline: 0,
    recovery: 0,
    reload: 0,
    teardown: 0,
    other: 0
  };
}

function classifyTarget(result, thresholds) {
  const findings = [];
  const candidates = [];
  const diagnostics = [];
  const firstPartySockets = result.websockets.filter((item) => item.first_party);

  const duplicates = result.snapshots.filter((snap) =>
    Object.values(snap.active_first_party_websockets_by_url).some((count) => count > 1)
  );
  if (duplicates.length) {
    findings.push({
      id: 'duplicate-active-first-party-websockets',
      verdict: 'SUPPORTED',
      severity: 'HIGH_RELIABILITY',
      evidence: `${duplicates.length} lifecycle snapshots contained more than one active first-party WebSocket for the same normalized URL.`
    });
  }

  const zombieAfterReload = firstPartySockets.filter((socket) =>
    socket.generation < result.reload_generation &&
    socket.closed_at_ms === null &&
    result.finished_at_ms - result.reload_started_at_ms >= thresholds.zombie_after_reload_grace_ms
  );
  if (zombieAfterReload.length) {
    findings.push({
      id: 'first-party-websocket-survives-reload',
      verdict: 'SUPPORTED',
      severity: 'HIGH_RELIABILITY',
      evidence: `${zombieAfterReload.length} first-party WebSocket connection(s) created before reload remained open beyond the configured grace period.`
    });
  }

  const zombieAfterBlank = firstPartySockets.filter((socket) =>
    socket.created_at_ms < result.teardown_started_at_ms && socket.closed_at_ms === null
  );
  const framesAfterBlank = firstPartySockets.reduce(
    (sum, socket) => sum + (socket.frames_received_by_phase.teardown || 0) + (socket.frames_sent_by_phase.teardown || 0),
    0
  );
  if (zombieAfterBlank.length || framesAfterBlank > 0) {
    findings.push({
      id: 'first-party-transport-survives-navigation-away',
      verdict: 'SUPPORTED',
      severity: 'HIGH_RELIABILITY',
      evidence: `${zombieAfterBlank.length} first-party WebSocket(s) remained open and ${framesAfterBlank} frame(s) were observed after navigation to about:blank.`
    });
  }

  const recoveryCreates = firstPartySockets
    .filter((socket) => socket.created_phase === 'recovery')
    .map((socket) => socket.created_at_ms)
    .sort((a, b) => a - b);
  const recoveryIntervals = recoveryCreates.slice(1).map((value, index) => value - recoveryCreates[index]);
  if (
    recoveryCreates.length >= thresholds.reconnect_storm_creates &&
    median(recoveryIntervals) !== null &&
    median(recoveryIntervals) < thresholds.reconnect_storm_median_interval_ms
  ) {
    findings.push({
      id: 'first-party-reconnect-storm',
      verdict: 'SUPPORTED',
      severity: 'HIGH_RELIABILITY',
      evidence: `${recoveryCreates.length} first-party WebSocket creations occurred during recovery with median spacing ${round(median(recoveryIntervals), 0)} ms.`
    });
  }

  for (const [url, stats] of Object.entries(result.first_party_request_stats)) {
    const errorCount = Object.entries(stats.status_counts)
      .filter(([status]) => Number(status) >= 400)
      .reduce((sum, [, count]) => sum + count, 0);
    if (errorCount >= thresholds.repeated_first_party_error_count) {
      findings.push({
        id: `repeated-first-party-error-${sha256(url).slice(0, 12)}`,
        verdict: 'SUPPORTED',
        severity: 'MEDIUM_RELIABILITY',
        evidence: `${url} returned ${errorCount} first-party HTTP error responses during one bounded lifecycle run.`
      });
    }
    if (stats.max_concurrent >= thresholds.overlapping_identical_requests) {
      candidates.push({
        id: `overlapping-identical-request-${sha256(url).slice(0, 12)}`,
        verdict: 'NEEDS_EVIDENCE',
        evidence: `${url} reached ${stats.max_concurrent} concurrent identical requests; product intent and user impact are not established.`
      });
    }
  }

  const realtimeBefore = result.realtime_activity.bootstrap > 0;
  const realtimeAfter = result.realtime_activity.recovery > 0;
  const retainedVisibleState = result.snapshots.some((snap) => snap.phase === 'offline' && snap.visible_chart_or_quote);
  const explicitOfflineState = result.snapshots.some((snap) => snap.phase === 'offline' && snap.connection_state_visible);
  if (realtimeBefore && realtimeAfter && retainedVisibleState && !explicitOfflineState) {
    candidates.push({
      id: 'stale-state-indicator-gap',
      verdict: 'NEEDS_EVIDENCE',
      evidence: 'Realtime-like activity existed before and after the outage, while chart/quote state remained visible during offline mode without explicit stale/offline/reconnecting language.'
    });
  }

  if (!firstPartySockets.length) {
    diagnostics.push({
      id: 'no-first-party-websocket-observed',
      verdict: 'NOT_A_DEFECT',
      evidence: 'No first-party WebSocket was naturally initiated by this public page during the bounded run; zombie-WebSocket behavior is therefore not testable on this surface in this session.'
    });
  }

  if (!findings.length && firstPartySockets.length) {
    diagnostics.push({
      id: 'clean-first-party-websocket-lifecycle',
      verdict: 'PASS',
      evidence: 'No duplicate active first-party socket, reconnect storm, reload survivor, or post-navigation survivor crossed the deterministic thresholds.'
    });
  }

  return { findings, candidates, diagnostics };
}

async function observeTarget(browser, config, target, outputDir) {
  const profile = config.profiles[target.profile];
  if (!profile) throw new Error(`missing profile ${target.profile}`);

  const page = await browser.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  const client = await page.target().createCDPSession();
  await client.send('Network.enable');
  await client.send('Performance.enable');
  await client.send('Emulation.setCPUThrottlingRate', { rate: profile.cpu_throttling_rate });

  const onlineNetwork = {
    offline: false,
    latency: profile.network.latency_ms,
    downloadThroughput: profile.network.download_bytes_per_second,
    uploadThroughput: profile.network.upload_bytes_per_second,
    connectionType: profile.network.connection_type
  };
  await client.send('Network.emulateNetworkConditions', onlineNetwork);

  const startedAt = Date.now();
  let phase = 'bootstrap';
  let generation = 1;
  const reloadGeneration = 2;
  let reloadStartedAt = null;
  let teardownStartedAt = null;

  const websockets = new Map();
  const activeRequests = new Map();
  const requestStats = new Map();
  const snapshots = [];
  const consoleEvents = [];
  const pageErrors = [];
  const eventSourceCounts = phaseCounter();
  const realtimeActivity = phaseCounter();

  const now = () => Date.now() - startedAt;
  const countRealtime = (eventPhase) => {
    realtimeActivity[eventPhase] = (realtimeActivity[eventPhase] || 0) + 1;
  };

  function ensureRequestStats(url) {
    if (!requestStats.has(url)) {
      requestStats.set(url, {
        count: 0,
        in_flight: 0,
        max_concurrent: 0,
        status_counts: {},
        phases: phaseCounter(),
        types: {}
      });
    }
    return requestStats.get(url);
  }

  client.on('Network.webSocketCreated', ({ requestId, url }) => {
    const normalized = safeUrl(url);
    websockets.set(requestId, {
      request_id_hash: sha256(requestId).slice(0, 16),
      url: normalized,
      first_party: isTradernet(url),
      generation,
      created_at_ms: now(),
      created_phase: phase,
      handshake_status: null,
      closed_at_ms: null,
      close_phase: null,
      frames_received: 0,
      frames_sent: 0,
      bytes_received: 0,
      bytes_sent: 0,
      frames_received_by_phase: phaseCounter(),
      frames_sent_by_phase: phaseCounter()
    });
  });

  client.on('Network.webSocketHandshakeResponseReceived', ({ requestId, response }) => {
    const socket = websockets.get(requestId);
    if (socket) socket.handshake_status = response.status;
  });

  client.on('Network.webSocketFrameReceived', ({ requestId, response }) => {
    const socket = websockets.get(requestId);
    if (!socket) return;
    const length = Buffer.byteLength(response.payloadData || '', 'utf8');
    socket.frames_received += 1;
    socket.bytes_received += length;
    socket.frames_received_by_phase[phase] = (socket.frames_received_by_phase[phase] || 0) + 1;
    if (socket.first_party) countRealtime(phase);
  });

  client.on('Network.webSocketFrameSent', ({ requestId, response }) => {
    const socket = websockets.get(requestId);
    if (!socket) return;
    const length = Buffer.byteLength(response.payloadData || '', 'utf8');
    socket.frames_sent += 1;
    socket.bytes_sent += length;
    socket.frames_sent_by_phase[phase] = (socket.frames_sent_by_phase[phase] || 0) + 1;
  });

  client.on('Network.webSocketClosed', ({ requestId }) => {
    const socket = websockets.get(requestId);
    if (!socket) return;
    socket.closed_at_ms = now();
    socket.close_phase = phase;
  });

  client.on('Network.eventSourceMessageReceived', () => {
    eventSourceCounts[phase] = (eventSourceCounts[phase] || 0) + 1;
    countRealtime(phase);
  });

  client.on('Network.requestWillBeSent', ({ requestId, request, type }) => {
    if (!isTradernet(request.url)) return;
    const normalized = safeUrl(request.url);
    const stats = ensureRequestStats(normalized);
    stats.count += 1;
    stats.in_flight += 1;
    stats.max_concurrent = Math.max(stats.max_concurrent, stats.in_flight);
    stats.phases[phase] = (stats.phases[phase] || 0) + 1;
    stats.types[type] = (stats.types[type] || 0) + 1;
    activeRequests.set(requestId, { url: normalized, type, started_phase: phase });
    if (/quote|hloc|market|ticker|price|trade/i.test(normalized) && ['XHR', 'Fetch', 'EventSource'].includes(type)) {
      countRealtime(phase);
    }
  });

  client.on('Network.responseReceived', ({ requestId, response }) => {
    const active = activeRequests.get(requestId);
    if (!active) return;
    const stats = ensureRequestStats(active.url);
    const key = String(response.status);
    stats.status_counts[key] = (stats.status_counts[key] || 0) + 1;
  });

  function finishRequest(requestId) {
    const active = activeRequests.get(requestId);
    if (!active) return;
    const stats = ensureRequestStats(active.url);
    stats.in_flight = Math.max(0, stats.in_flight - 1);
    activeRequests.delete(requestId);
  }
  client.on('Network.loadingFinished', ({ requestId }) => finishRequest(requestId));
  client.on('Network.loadingFailed', ({ requestId }) => finishRequest(requestId));

  page.on('console', (message) => {
    if (consoleEvents.length >= 40) return;
    const text = message.text().replace(/https?:\/\/[^\s]+/g, (value) => safeUrl(value)).slice(0, 500);
    consoleEvents.push({ at_ms: now(), phase, type: message.type(), text_sha256: sha256(text), text_preview: text });
  });
  page.on('pageerror', (error) => {
    if (pageErrors.length >= 20) return;
    const text = String(error?.message || error).slice(0, 500);
    pageErrors.push({ at_ms: now(), phase, text_sha256: sha256(text), text_preview: text });
  });

  async function snapshot(label) {
    const dom = await page.evaluate(() => {
      const text = (document.body?.innerText || '').toLowerCase();
      const visible = (element) => {
        if (!(element instanceof Element)) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
      };
      const canvases = [...document.querySelectorAll('canvas')];
      const quoteLike = [...document.querySelectorAll('[class*="price" i], [class*="quote" i], [data-price], canvas')].some(visible);
      const connectionTerms = ['offline', 'disconnected', 'reconnecting', 'connection lost', 'нет соединения', 'офлайн', 'переподключ'];
      return {
        url: location.href,
        title: document.title,
        canvas_count: canvases.length,
        visible_canvas_count: canvases.filter(visible).length,
        visible_chart_or_quote: quoteLike,
        connection_state_visible: connectionTerms.some((term) => text.includes(term)),
        market_closed_visible: text.includes('market closed') || text.includes('рынок закрыт')
      };
    }).catch(() => ({
      url: page.url(),
      title: '',
      canvas_count: 0,
      visible_canvas_count: 0,
      visible_chart_or_quote: false,
      connection_state_visible: false,
      market_closed_visible: false
    }));

    const metrics = await client.send('Performance.getMetrics').catch(() => ({ metrics: [] }));
    const metricMap = Object.fromEntries((metrics.metrics || []).map((item) => [item.name, item.value]));
    const activeByUrl = {};
    for (const socket of websockets.values()) {
      if (!socket.first_party || socket.closed_at_ms !== null) continue;
      activeByUrl[socket.url] = (activeByUrl[socket.url] || 0) + 1;
    }
    snapshots.push({
      label,
      at_ms: now(),
      phase,
      generation,
      active_first_party_websockets_by_url: activeByUrl,
      active_first_party_websocket_count: Object.values(activeByUrl).reduce((sum, count) => sum + count, 0),
      active_first_party_request_count: activeRequests.size,
      js_heap_used_bytes: metricMap.JSHeapUsedSize ?? null,
      documents: metricMap.Documents ?? null,
      nodes: metricMap.Nodes ?? null,
      ...dom
    });
  }

  async function waitWithSnapshots(duration, prefix) {
    const interval = config.timings_ms.snapshot_interval;
    const cycles = Math.max(1, Math.ceil(duration / interval));
    for (let index = 0; index < cycles; index += 1) {
      await sleep(Math.min(interval, duration - index * interval));
      await snapshot(`${prefix}-${index + 1}`);
    }
  }

  let navigationStatus = null;
  try {
    const response = await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    navigationStatus = response?.status() ?? null;
    await waitWithSnapshots(config.timings_ms.bootstrap, 'bootstrap');

    phase = 'offline';
    await client.send('Network.emulateNetworkConditions', { ...onlineNetwork, offline: true });
    await waitWithSnapshots(config.timings_ms.offline, 'offline');

    phase = 'recovery';
    await client.send('Network.emulateNetworkConditions', onlineNetwork);
    await waitWithSnapshots(config.timings_ms.recovery, 'recovery');

    phase = 'reload';
    generation = reloadGeneration;
    reloadStartedAt = now();
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitWithSnapshots(config.timings_ms.post_reload, 'reload');

    phase = 'teardown';
    generation += 1;
    teardownStartedAt = now();
    await page.goto('about:blank', { waitUntil: 'load', timeout: 30000 });
    await waitWithSnapshots(config.timings_ms.post_navigation_teardown, 'teardown');
  } finally {
    await client.send('Network.emulateNetworkConditions', onlineNetwork).catch(() => {});
  }

  const finishedAt = now();
  const result = {
    schema_version: 'liminalqa-tradernet-connection-lifecycle-result-v1',
    target_id: target.id,
    target_role: target.role,
    requested_url: target.url,
    final_url_before_teardown: snapshots.filter((item) => item.phase !== 'teardown').at(-1)?.url || null,
    navigation_status: navigationStatus,
    started_at_utc: new Date(startedAt).toISOString(),
    finished_at_ms: finishedAt,
    reload_started_at_ms: reloadStartedAt,
    reload_generation: reloadGeneration,
    teardown_started_at_ms: teardownStartedAt,
    profile_id: target.profile,
    websockets: [...websockets.values()],
    event_source_messages_by_phase: eventSourceCounts,
    realtime_activity: realtimeActivity,
    first_party_request_stats: Object.fromEntries([...requestStats.entries()].sort(([a], [b]) => a.localeCompare(b))),
    snapshots,
    console_events: consoleEvents,
    page_errors: pageErrors
  };
  result.lotus = classifyTarget(result, config.thresholds);

  const targetDir = path.join(outputDir, target.id);
  fs.mkdirSync(targetDir, { recursive: true });
  fs.writeFileSync(path.join(targetDir, 'connection-lifecycle.json'), `${JSON.stringify(result, null, 2)}\n`);
  await page.screenshot({ path: path.join(targetDir, 'final-before-close.png'), fullPage: true }).catch(() => {});
  await page.close();
  return result;
}

function buildSummary(config, results) {
  const lines = [
    '# Tradernet public connection lifecycle audit',
    '',
    `Targets: ${results.length}`,
    '',
    '| Target | First-party WS | WS frames | Confirmed findings | Candidates | Verdict |',
    '|---|---:|---:|---:|---:|---|'
  ];
  for (const result of results) {
    const firstParty = result.websockets.filter((item) => item.first_party);
    const frames = firstParty.reduce((sum, item) => sum + item.frames_received + item.frames_sent, 0);
    const verdict = result.lotus.findings.length
      ? 'SUPPORTED_FINDING'
      : result.lotus.candidates.length
        ? 'NEEDS_EVIDENCE'
        : firstParty.length
          ? 'PASS'
          : 'NOT_TESTABLE_NO_FIRST_PARTY_WS';
    lines.push(`| ${result.target_id} | ${firstParty.length} | ${frames} | ${result.lotus.findings.length} | ${result.lotus.candidates.length} | ${verdict} |`);
  }
  lines.push('', '## Decision boundary', '');
  lines.push('- A zombie connection requires an old first-party connection to remain active after reload or navigation-away beyond the configured grace period.');
  lines.push('- A reconnect storm requires at least five first-party WebSocket creations during recovery with median spacing below three seconds.');
  lines.push('- No live-data absence claim is made outside an active market session.');
  lines.push('- Third-party telemetry is diagnostic only and cannot create a Tradernet product finding.');
  return `${lines.join('\n')}\n`;
}

async function main() {
  const args = parseArgs(process.argv);
  const config = JSON.parse(fs.readFileSync(args.config, 'utf8'));
  const outputDir = path.resolve(args['output-dir']);
  fs.mkdirSync(outputDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking']
  });

  const results = [];
  try {
    for (const target of config.targets) {
      results.push(await observeTarget(browser, config, target, outputDir));
    }
  } finally {
    await browser.close();
  }

  const aggregate = {
    schema_version: 'liminalqa-tradernet-connection-lifecycle-aggregate-v1',
    config_sha256: sha256(JSON.stringify(config)),
    target_count: results.length,
    confirmed_findings: results.flatMap((item) => item.lotus.findings.map((finding) => ({ target_id: item.target_id, ...finding }))),
    candidates: results.flatMap((item) => item.lotus.candidates.map((finding) => ({ target_id: item.target_id, ...finding }))),
    diagnostics: results.flatMap((item) => item.lotus.diagnostics.map((finding) => ({ target_id: item.target_id, ...finding }))),
    authority: {
      mode: 'audit_only',
      ownership: false,
      approval: false,
      execution: false,
      delivery: false,
      external_submission: false,
      merge: false
    }
  };
  fs.writeFileSync(path.join(outputDir, 'aggregate.json'), `${JSON.stringify(aggregate, null, 2)}\n`);
  fs.writeFileSync(path.join(outputDir, 'summary.md'), buildSummary(config, results));
  fs.writeFileSync(path.join(outputDir, 'manifest.sha256'), [
    `${sha256(fs.readFileSync(path.join(outputDir, 'aggregate.json')))}  aggregate.json`,
    `${sha256(fs.readFileSync(path.join(outputDir, 'summary.md')))}  summary.md`
  ].join('\n') + '\n');

  console.log(buildSummary(config, results));
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});
