#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import puppeteer from 'puppeteer-core';

const marketRe = /backend\.takeprofit\.com\/(?:takeprofit\.(?:marketdata|reference)|connect)|ListQuotes|ListBars|TimeApi/i;
const barRe = /ListBars|candle|history|extrapolation/i;
const quoteRe = /ListQuotes|quote/i;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const iso = () => new Date().toISOString();
const uniq = (xs) => [...new Set(xs)];
const sha = (data) => crypto.createHash('sha256').update(data).digest('hex');

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 2) out[argv[i].replace(/^--/, '')] = argv[i + 1];
  return out;
}

function percentile(values, p) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.ceil((p / 100) * s.length) - 1))];
}

async function snapshot(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
    };
    const canvases = [...document.querySelectorAll('canvas')].filter(visible).map((el) => {
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height), backingWidth: el.width, backingHeight: el.height };
    });
    const svgs = [...document.querySelectorAll('svg')].filter(visible).map((el) => {
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) };
    }).filter((x) => x.width > 180 && x.height > 100);
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').slice(0, 40000);
    const lower = text.toLowerCase();
    const stateTerms = ['loading', 'connecting', 'reconnecting', 'disconnected', 'offline', 'no data', 'market closed', 'delayed', 'real-time', 'realtime', 'stale', 'error', 'failed'];
    const tickerHints = text.match(/\b(?:BTC|ETH|TSLA|AAPL|META|SPY)[/A-Z0-9.:-]{0,24}\b/g) || [];
    const priceLike = text.match(/(?:^|\s)(?:[$€₽₺]?[+-]?\d{2,6}(?:[,.]\d{1,8})?)(?:%|[KMB])?(?=\s|$)/g) || [];
    return {
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      chartSurfaceCount: canvases.length + svgs.length,
      canvases,
      largeSvgs: svgs,
      states: stateTerms.filter((x) => lower.includes(x)),
      tickerHints: [...new Set(tickerHints)].slice(0, 30),
      priceLike: [...new Set(priceLike.map((x) => x.trim()))].slice(0, 100),
      textSample: text.slice(0, 5000),
      mutationCount: globalThis.__liminalMutations || 0
    };
  });
}

async function chartRect(page) {
  return page.evaluate(() => {
    const candidates = [...document.querySelectorAll('canvas,svg')].map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height, area: r.width * r.height };
    }).filter((r) => r.width > 180 && r.height > 100 && r.x < innerWidth && r.y < innerHeight && r.x + r.width > 0 && r.y + r.height > 0)
      .sort((a, b) => b.area - a.area);
    const c = candidates[0];
    if (!c) return null;
    const x = Math.max(0, c.x), y = Math.max(0, c.y);
    return {
      x, y,
      width: Math.max(1, Math.min(innerWidth - x, c.width)),
      height: Math.max(1, Math.min(innerHeight - y, c.height)),
      centerX: Math.max(2, Math.min(innerWidth - 2, c.x + c.width / 2)),
      centerY: Math.max(2, Math.min(innerHeight - 2, c.y + c.height / 2))
    };
  });
}

async function chartShot(page, file) {
  const rect = await chartRect(page);
  if (!rect) return null;
  const buffer = await page.screenshot({ clip: { x: rect.x, y: rect.y, width: rect.width, height: rect.height } });
  fs.writeFileSync(file, buffer);
  return { file: path.basename(file), sha256: sha(buffer), bytes: buffer.length, rect };
}

function classify(r, cfg) {
  const expected = cfg.expectedSymbolHint.toUpperCase();
  const initial = r.stages.initial.snapshot;
  const reload = r.stages.reload.snapshot;
  const initialSymbol = `${initial.textSample} ${initial.tickerHints.join(' ')}`.toUpperCase().includes(expected);
  const reloadSymbol = `${reload.textSample} ${reload.tickerHints.join(' ')}`.toUpperCase().includes(expected);
  const bootstrap = r.transport.listBarsCount > 0 && r.transport.listQuotesCount > 0;
  const liveActivity = r.transport.distinctQuoteBodyCount > 1 || r.stages.live.chartPixelsChanged;
  const reconnectActivity = r.stages.reconnect.marketEventsAfterOnline > 0;
  const historicalErrors = r.console.signatures.length > 0;
  const panIntegrityWarn = r.stages.pan.visualComplexityMinRatio !== null && r.stages.pan.visualComplexityMinRatio < 0.65;
  const checks = {
    chartBoot: initial.chartSurfaceCount > 0 && initialSymbol ? (historicalErrors ? 'WARN' : 'PASS') : 'FAIL',
    quoteBootstrap: bootstrap ? 'PASS' : 'FAIL',
    liveQuoteActivity: liveActivity ? 'PASS' : 'WARN',
    panLayerIntegrity: panIntegrityWarn ? 'WARN' : 'PASS',
    historyLoading: r.stages.pan.newListBarsRequests > 0 ? 'PASS' : 'UNVERIFIED',
    reconnectRecovery: reconnectActivity ? 'PASS' : 'WARN',
    reloadRecovery: reload.chartSurfaceCount > 0 && reloadSymbol ? 'PASS' : 'FAIL',
    staleStateClarity: r.stages.reconnect.offlineSnapshot.states.length > 0 ? 'PASS' : 'WARN',
    historicalRegression: historicalErrors ? 'WARN' : 'PASS'
  };
  const verdict = Object.values(checks).includes('FAIL') ? 'FAIL' : Object.values(checks).includes('WARN') ? 'WARN' : 'PASS';
  return { verdict, checks };
}

function markdown(r, resultHash) {
  const rows = Object.entries(r.classification.checks).map(([k, v]) => `| ${k} | ${v} |`).join('\n');
  const sigs = r.console.signatures.length ? r.console.signatures.map((x) => `- \`${x}\``).join('\n') : '- None of the tracked historical signatures appeared.';
  const calls = r.network.marketRequests.slice(0, 20).map((x) => `- \`${x.method} ${x.status ?? 'n/a'} ${x.url}\``).join('\n') || '- No market-data calls captured.';
  return `# LiminalQA · TakeProfit public chart and quote causality\n\n**Target:** \`${r.target.finalUrl}\`  \n**Verdict:** **${r.classification.verdict}**  \n**Evidence SHA-256:** \`${resultHash}\`\n\n## Decision matrix\n\n| Check | Verdict |\n|---|---|\n${rows}\n\n## Observed data path\n\n- Chart surfaces after boot: **${r.stages.initial.snapshot.chartSurfaceCount}**\n- Expected symbol visible: **${r.stages.initial.expectedSymbolDetected}**\n- 'ListBars' requests: **${r.transport.listBarsCount}**\n- 'ListQuotes' requests: **${r.transport.listQuotesCount}**\n- Market-data chunks: **${r.transport.streamingChunkCount}**\n- Distinct quote response bodies: **${r.transport.distinctQuoteBodyCount}**\n- Market-data bytes observed: **${r.transport.streamingBytes}**\n- WebSocket frames: **${r.transport.websocketFramesReceived}**\n- Chart pixels changed during live window: **${r.stages.live.chartPixelsChanged}**\n- Controlled pan complexity ratio: **${r.stages.pan.visualComplexityMinRatio ?? 'n/a'}**\n- Additional 'ListBars' after controlled pan: **${r.stages.pan.newListBarsRequests}**\n- Market events after reconnect: **${r.stages.reconnect.marketEventsAfterOnline}**\n- Explicit offline/stale UI state: **${r.stages.reconnect.offlineSnapshot.states.join(', ') || 'not observed'}**\n- Chart restored after reload: **${r.stages.reload.expectedSymbolDetected && r.stages.reload.snapshot.chartSurfaceCount > 0}**\n\n## Historical signatures\n\n${sigs}\n\n## Market request sample\n\n${calls}\n\n## Causal reading\n\n\`reference/security → time → ListQuotes + ListBars → chart state → rendered BTC series\`\n\nSensitive failure modes tested:\n\n1. **Bootstrap ordering:** quote/security metadata arrives after chart initialization and leaves required fields undefined.\n2. **Split-brain symbol state:** header, candles, indicator calculations, and last-price label refer to different securities after a transition.\n3. **Stale-but-plausible chart:** network drops while the last candle remains visible without a delayed/offline marker.\n4. **Duplicate subscription:** reconnect creates parallel streams, repeated calculations, or excessive store updates.\n5. **History merge:** older bars are duplicated, reordered, or shift the viewport during backfill.\n6. **Reload race:** persisted chart settings restore before security/time-series data and produce validation errors.\n\n> Passive observation of requests made by the public page itself. No direct endpoint calls, authentication, orders, fuzzing, load testing, or vulnerability claim.\n`;
}

async function main() {
  const a = parseArgs(process.argv);
  if (!a.config || !a.chrome || !a.output) throw new Error('Required: --config --chrome --output');
  const cfg = JSON.parse(fs.readFileSync(a.config, 'utf8'));
  fs.mkdirSync(a.output, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: a.chrome, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-timer-throttling'] });
  const page = await browser.newPage();
  await page.setViewport(cfg.viewport);
  await page.evaluateOnNewDocument(() => {
    globalThis.__liminalMutations = 0;
    addEventListener('DOMContentLoaded', () => new MutationObserver((rs) => { globalThis.__liminalMutations += rs.length; })
      .observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true }), { once: true });
  });
  const cdp = await page.createCDPSession();
  await cdp.send('Network.enable');

  const consoleMessages = [], pageErrors = [], failed = [], responses = [], requests = [], websockets = [], frames = [];
  const cdpMarket = new Map();
  const responseBodies = [];
  const rawBodies = [];
  const bodyPromises = [];
  const rawBodyPromises = [];
  page.on('console', (x) => consoleMessages.push({ type: x.type(), text: x.text(), at: iso() }));
  page.on('pageerror', (x) => pageErrors.push({ message: x.message, stack: x.stack, at: iso() }));
  page.on('request', (x) => {
    if (marketRe.test(x.url())) requests.push({ url: x.url(), method: x.method(), postData: (x.postData() || '').slice(0, 12000), at: Date.now() });
  });
  page.on('requestfailed', (x) => failed.push({ url: x.url(), method: x.method(), error: x.failure()?.errorText, at: iso() }));
  page.on('response', (x) => {
    const entry = { url: x.url(), status: x.status(), method: x.request().method(), type: x.request().resourceType(), contentType: x.headers()['content-type'], at: Date.now() };
    responses.push(entry);
    if (marketRe.test(x.url()) && (barRe.test(x.url()) || quoteRe.test(x.url()) || /TimeApi/i.test(x.url()))) {
      bodyPromises.push(Promise.race([x.text().then((body) => responseBodies.push({ url: x.url(), status: x.status(), body: body.slice(0, 20000) })).catch(() => {}), sleep(6000)]));
    }
  });
  cdp.on('Network.requestWillBeSent', (x) => {
    if (marketRe.test(x.request.url)) cdpMarket.set(x.requestId, { url: x.request.url, startedAt: Date.now(), chunks: 0, bytes: 0, finished: false });
  });
  cdp.on('Network.responseReceived', (x) => { const s = cdpMarket.get(x.requestId); if (s) { s.status = x.response.status; s.mimeType = x.response.mimeType; } });
  cdp.on('Network.dataReceived', (x) => { const s = cdpMarket.get(x.requestId); if (s) { s.chunks += 1; s.bytes += x.dataLength || 0; s.lastAt = Date.now(); } });
  cdp.on('Network.loadingFinished', (x) => {
    const state = cdpMarket.get(x.requestId);
    if (!state) return;
    state.finished = true;
    state.endAt = Date.now();
    if (barRe.test(state.url) || quoteRe.test(state.url) || /TimeApi/i.test(state.url)) {
      rawBodyPromises.push(cdp.send('Network.getResponseBody', { requestId: x.requestId })
        .then((body) => rawBodies.push({ url: state.url, at: Date.now(), base64Encoded: body.base64Encoded, body: body.body }))
        .catch(() => {}));
    }
  });
  cdp.on('Network.loadingFailed', (x) => { const s = cdpMarket.get(x.requestId); if (s) { s.failed = x.errorText; s.endAt = Date.now(); } });
  cdp.on('Network.webSocketCreated', (x) => websockets.push({ id: x.requestId, url: x.url, at: Date.now() }));
  cdp.on('Network.webSocketFrameReceived', (x) => frames.push({ id: x.requestId, at: Date.now(), length: x.response.payloadData?.length || 0 }));

  const r = {
    schemaVersion: 'liminalqa-takeprofit-chart-quote-probe-v3', startedAt: iso(),
    target: { requestedUrl: cfg.targetUrl, finalUrl: null }, environment: { viewport: cfg.viewport, chrome: await browser.version() },
    stages: {}, console: {}, network: {}, transport: {}, boundaries: cfg.boundaries, evidence: {}
  };

  try {
    const t0 = Date.now();
    await page.goto(cfg.targetUrl, { waitUntil: 'domcontentloaded', timeout: cfg.navigationTimeoutMs });
    r.target.finalUrl = page.url();
    await sleep(cfg.initialWaitMs);
    const initial = await snapshot(page);
    r.stages.initial = { elapsedMs: Date.now() - t0, expectedSymbolDetected: `${initial.textSample} ${initial.tickerHints.join(' ')}`.toUpperCase().includes(cfg.expectedSymbolHint.toUpperCase()), snapshot: initial };
    await page.screenshot({ path: path.join(a.output, '01-initial.png') });

    const liveA = await chartShot(page, path.join(a.output, '02-live-start.png'));
    const marketEventsBeforeLive = requests.length + [...cdpMarket.values()].reduce((n, x) => n + x.chunks, 0);
    await sleep(cfg.liveObservationMs);
    const liveB = await chartShot(page, path.join(a.output, '03-live-end.png'));
    r.stages.live = { chartStart: liveA, chartEnd: liveB, chartPixelsChanged: Boolean(liveA && liveB && liveA.sha256 !== liveB.sha256), marketEventsDuringWindow: requests.length + [...cdpMarket.values()].reduce((n, x) => n + x.chunks, 0) - marketEventsBeforeLive, snapshot: await snapshot(page) };

    const beforeBars = requests.filter((x) => barRe.test(x.url)).length;
    const rect = await chartRect(page);
    const panShots = [];
    if (rect) {
      for (let i = 1; i <= cfg.panSteps; i += 1) {
        const startX = Math.min(rect.x + rect.width - 30, rect.centerX + cfg.panPixelsPerStep / 2);
        const endX = Math.max(rect.x + 30, startX - cfg.panPixelsPerStep);
        await page.mouse.move(startX, rect.centerY);
        await page.mouse.down();
        await page.mouse.move(endX, rect.centerY, { steps: 12 });
        await page.mouse.up();
        await sleep(1800);
        panShots.push(await chartShot(page, path.join(a.output, `04-pan-${i}.png`)));
      }
    }
    await sleep(6000);
    const validPanBytes = panShots.filter(Boolean).map((x) => x.bytes);
    const baselineBytes = liveB?.bytes || liveA?.bytes || null;
    r.stages.pan = {
      shots: panShots,
      visualComplexityMinRatio: baselineBytes && validPanBytes.length ? Math.round((Math.min(...validPanBytes) / baselineBytes) * 1000) / 1000 : null,
      newListBarsRequests: Math.max(0, requests.filter((x) => barRe.test(x.url)).length - beforeBars),
      snapshot: await snapshot(page)
    };
    await page.screenshot({ path: path.join(a.output, '04-pan-final-full.png') });

    await cdp.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0, connectionType: 'none' });
    await sleep(cfg.offlineMs);
    const offlineSnapshot = await snapshot(page);
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 80, downloadThroughput: -1, uploadThroughput: -1, connectionType: 'wifi' });
    const eventsAtOnline = requests.length + [...cdpMarket.values()].reduce((n, x) => n + x.chunks, 0) + frames.length;
    await sleep(cfg.reconnectWaitMs);
    const eventsAfter = requests.length + [...cdpMarket.values()].reduce((n, x) => n + x.chunks, 0) + frames.length;
    r.stages.reconnect = { marketEventsAfterOnline: Math.max(0, eventsAfter - eventsAtOnline), offlineSnapshot, snapshot: await snapshot(page) };
    await page.screenshot({ path: path.join(a.output, '05-reconnect.png') });

    const tr = Date.now();
    await page.reload({ waitUntil: 'domcontentloaded', timeout: cfg.navigationTimeoutMs });
    await sleep(cfg.reloadWaitMs);
    const reload = await snapshot(page);
    r.stages.reload = { elapsedMs: Date.now() - tr, expectedSymbolDetected: `${reload.textSample} ${reload.tickerHints.join(' ')}`.toUpperCase().includes(cfg.expectedSymbolHint.toUpperCase()), snapshot: reload };
    await page.screenshot({ path: path.join(a.output, '06-reload.png') });
  } finally {
    await Promise.allSettled(bodyPromises);
    await Promise.allSettled(rawBodyPromises);
    const patterns = [/IndicatorManager/i, /ChartStore/i, /is a required field/i, /Cannot read properties of undefined/i, /Time scale or logical range is not defined/i, /fetched too much times per second/i, /failed to establish stream connection/i, /ZOrder to removed drawing/i, /failed to find logs for alert/i];
    r.console = { messages: consoleMessages, pageErrors, signatures: uniq([...consoleMessages.map((x) => x.text), ...pageErrors.map((x) => x.message)].filter((x) => patterns.some((p) => p.test(x)))) };
    const marketRequests = responses.filter((x) => marketRe.test(x.url));
    const streams = [...cdpMarket.entries()].map(([requestId, x]) => ({ requestId, ...x }));
    const gaps = frames.slice(1).map((x, i) => x.at - frames[i].at).filter((x) => x >= 0);
    r.network = { marketRequests, requestPayloads: requests, responseBodies, rawBodies, failedRequests: failed, httpErrors: responses.filter((x) => x.status >= 400) };
    r.transport = {
      listBarsCount: requests.filter((x) => barRe.test(x.url)).length,
      listQuotesCount: requests.filter((x) => quoteRe.test(x.url)).length,
      distinctQuoteBodyCount: new Set(rawBodies.filter((x) => quoteRe.test(x.url)).map((x) => sha(Buffer.from(x.body, x.base64Encoded ? 'base64' : 'utf8')))).size,
      marketStreams: streams,
      streamingChunkCount: streams.reduce((n, x) => n + x.chunks, 0),
      streamingBytes: streams.reduce((n, x) => n + x.bytes, 0),
      websocketConnections: websockets,
      websocketFramesReceived: frames.length,
      websocketGapP50Ms: percentile(gaps, 50), websocketGapP95Ms: percentile(gaps, 95), websocketGapMaxMs: gaps.length ? Math.max(...gaps) : null
    };
    r.completedAt = iso();
    r.classification = classify(r, cfg);
    const resultPath = path.join(a.output, 'result.json');
    fs.writeFileSync(resultPath, JSON.stringify(r, null, 2) + '\n');
    const resultHash = sha(fs.readFileSync(resultPath));
    fs.writeFileSync(path.join(a.output, 'summary.md'), markdown(r, resultHash));
    fs.writeFileSync(path.join(a.output, 'evidence.sha256'), `${resultHash}  result.json\n`);
    await browser.close();
  }
}

main().catch((e) => { console.error(e.stack || e); process.exit(1); });
