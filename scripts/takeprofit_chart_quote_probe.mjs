#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import puppeteer from 'puppeteer-core';

function args(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 2) out[argv[i].replace(/^--/, '')] = argv[i + 1];
  return out;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const iso = () => new Date().toISOString();
const uniq = (xs) => [...new Set(xs)];
const pct = (xs, p) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)];
};

async function snap(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden';
    };
    const canvases = [...document.querySelectorAll('canvas')].filter(visible).map((el) => {
      const r = el.getBoundingClientRect();
      return { width: Math.round(r.width), height: Math.round(r.height), backingWidth: el.width, backingHeight: el.height };
    });
    const svgs = [...document.querySelectorAll('svg')].filter(visible).map((el) => {
      const r = el.getBoundingClientRect();
      return { width: Math.round(r.width), height: Math.round(r.height) };
    }).filter((x) => x.width > 180 && x.height > 100);
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').slice(0, 30000);
    const states = ['loading', 'connecting', 'reconnecting', 'disconnected', 'offline', 'no data', 'market closed', 'delayed', 'real-time', 'realtime', 'error', 'failed']
      .filter((x) => text.toLowerCase().includes(x));
    const tickers = text.match(/\b(?:BTC|ETH|TSLA|AAPL|META|SPY)[/A-Z0-9.:-]{0,18}\b/g) || [];
    const nums = text.match(/(?:^|\s)(?:[$€₽₺]?[+-]?\d[\d,.]*)(?:%|[KMB])?(?=\s|$)/g) || [];
    return {
      url: location.href,
      title: document.title,
      readyState: document.readyState,
      chartSurfaceCount: canvases.length + svgs.length,
      canvases,
      largeSvgs: svgs,
      states,
      tickerHints: [...new Set(tickers)].slice(0, 30),
      numericTokenSample: [...new Set(nums.map((x) => x.trim()))].slice(0, 80),
      textSample: text.slice(0, 4000),
      mutationCount: globalThis.__liminalMutations || 0
    };
  });
}

async function chartPoint(page) {
  return page.evaluate(() => {
    const c = [...document.querySelectorAll('canvas,svg')].map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height, area: r.width * r.height };
    }).filter((r) => r.width > 180 && r.height > 100 && r.x < innerWidth && r.y < innerHeight)
      .sort((a, b) => b.area - a.area)[0];
    return c ? { x: Math.max(2, Math.min(innerWidth - 2, c.x + c.width / 2)), y: Math.max(2, Math.min(innerHeight - 2, c.y + c.height / 2)) } : null;
  });
}

function classify(r) {
  const chart = r.stages.initial?.snapshot?.chartSurfaceCount > 0;
  const reload = r.stages.reload?.snapshot?.chartSurfaceCount > 0;
  const checks = {
    chartBoot: chart ? (r.console.pageErrors.length ? 'WARN' : 'PASS') : 'FAIL',
    quoteTransport: r.transport.websocketFramesReceived > 0 ? 'PASS' : 'UNVERIFIED',
    tickerSwitch: r.stages.tickerSwitch?.detected ? 'PASS' : 'UNVERIFIED',
    reloadRecovery: reload ? 'PASS' : 'FAIL',
    reconnectRecovery: r.stages.reconnect?.websocketFramesAfterOnline > 0 ? 'PASS' : (r.transport.websocketFramesReceived > 0 ? 'WARN' : 'UNVERIFIED'),
    historyLoading: r.stages.historyScroll?.newMarketRequests > 0 ? 'PASS' : 'UNVERIFIED',
    stateClarity: r.stateSignals.detected.length ? 'PASS' : 'WARN'
  };
  const verdict = Object.values(checks).includes('FAIL') ? 'FAIL' : Object.values(checks).includes('WARN') ? 'WARN' : 'PASS';
  return { verdict, checks };
}

function md(r) {
  const rows = Object.entries(r.classification.checks).map(([k, v]) => `| ${k} | ${v} |`).join('\n');
  const sigs = r.console.signatures.length ? r.console.signatures.map((x) => `- \`${x}\``).join('\n') : '- No targeted historical signatures captured.';
  const reqs = r.network.marketDataRequests.slice(0, 12).map((x) => `- \`${x.method} ${x.status ?? 'n/a'} ${x.url}\``).join('\n') || '- None classified.';
  return `# LiminalQA · TakeProfit chart and quote probe\n\n**Target:** \`${r.target.finalUrl}\`  \n**Verdict:** **${r.classification.verdict}**  \n**Started:** ${r.startedAt}  \n**Completed:** ${r.completedAt}\n\n## Decision matrix\n\n| Check | Verdict |\n|---|---|\n${rows}\n\n## Core observations\n\n- Initial chart surfaces: **${r.stages.initial?.snapshot?.chartSurfaceCount ?? 0}**\n- Reload chart surfaces: **${r.stages.reload?.snapshot?.chartSurfaceCount ?? 0}**\n- WebSocket frames: **${r.transport.websocketFramesReceived}**\n- WebSocket p95 gap: **${r.transport.websocketGapP95Ms ?? 'n/a'} ms**\n- Market-data-like requests: **${r.network.marketDataRequests.length}**\n- Failed requests: **${r.network.failedRequests.length}**\n- HTTP errors: **${r.network.httpErrors.length}**\n- Page errors: **${r.console.pageErrors.length}**\n- Symbol switch detected: **${r.stages.tickerSwitch?.detected ?? false}**\n- New requests after history scroll: **${r.stages.historyScroll?.newMarketRequests ?? 0}**\n- Frames after reconnect: **${r.stages.reconnect?.websocketFramesAfterOnline ?? 0}**\n\n## Historical signatures\n\n${sigs}\n\n## Market-data request sample\n\n${reqs}\n\n## State signals\n\n${r.stateSignals.detected.length ? r.stateSignals.detected.map((x) => `\`${x}\``).join(', ') : 'No explicit loading/offline/delayed state found.'}\n\n## Causal interpretation\n\n1. History/bootstrap data must produce a visible chart surface.\n2. Streaming traffic must converge into current bars or an explicit delayed/offline state.\n3. Symbol change must invalidate old state before applying the new series.\n4. Reload and reconnect must rebuild subscriptions without duplicate streams, stale labels, or blank canvases.\n5. Scrolling left should request older bars once and preserve viewport continuity.\n\n> Passive browser-local QA on a public page. No authentication, orders, financial operations, endpoint fuzzing, load testing, or vulnerability claim.\n`;
}

async function main() {
  const a = args(process.argv);
  if (!a.config || !a.chrome || !a.output) throw new Error('Required: --config --chrome --output');
  const cfg = JSON.parse(fs.readFileSync(a.config, 'utf8'));
  fs.mkdirSync(a.output, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: a.chrome, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-timer-throttling'] });
  const page = await browser.newPage();
  await page.setViewport(cfg.viewport);
  await page.evaluateOnNewDocument(() => {
    globalThis.__liminalMutations = 0;
    addEventListener('DOMContentLoaded', () => {
      new MutationObserver((rs) => { globalThis.__liminalMutations += rs.length; })
        .observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
    }, { once: true });
  });
  const cdp = await page.createCDPSession();
  await cdp.send('Network.enable');
  const consoleMessages = [], pageErrors = [], failed = [], responses = [], sockets = [], frames = [];
  page.on('console', (x) => consoleMessages.push({ type: x.type(), text: x.text(), at: iso() }));
  page.on('pageerror', (x) => pageErrors.push({ message: x.message, stack: x.stack, at: iso() }));
  page.on('requestfailed', (x) => failed.push({ url: x.url(), method: x.method(), error: x.failure()?.errorText, at: iso() }));
  page.on('response', (x) => responses.push({ url: x.url(), status: x.status(), method: x.request().method(), type: x.request().resourceType(), at: iso() }));
  cdp.on('Network.webSocketCreated', (x) => sockets.push({ id: x.requestId, url: x.url, at: Date.now() }));
  cdp.on('Network.webSocketFrameReceived', (x) => frames.push({ id: x.requestId, at: Date.now(), opcode: x.response.opcode, length: x.response.payloadData?.length || 0 }));
  const r = {
    schemaVersion: 'liminalqa-takeprofit-chart-quote-probe-v1', startedAt: iso(),
    target: { requestedUrl: cfg.targetUrl, finalUrl: null }, environment: { viewport: cfg.viewport, chrome: await browser.version() },
    stages: {}, console: {}, network: {}, transport: {}, stateSignals: { detected: [] }, boundaries: cfg.boundaries
  };
  try {
    const t0 = Date.now();
    await page.goto(cfg.targetUrl, { waitUntil: 'domcontentloaded', timeout: cfg.navigationTimeoutMs });
    r.target.finalUrl = page.url();
    await sleep(cfg.initialWaitMs);
    r.stages.initial = { elapsedMs: Date.now() - t0, snapshot: await snap(page) };
    await page.screenshot({ path: path.join(a.output, '01-initial.png') });

    const before = await snap(page);
    await page.keyboard.press('Escape');
    const p = await chartPoint(page);
    if (p) await page.mouse.click(p.x, p.y);
    await page.keyboard.type(cfg.switchSymbol, { delay: 80 });
    await sleep(2500);
    await page.keyboard.press('Enter');
    await sleep(cfg.postSwitchWaitMs);
    const after = await snap(page);
    r.stages.tickerSwitch = { requested: cfg.switchSymbol, detected: `${after.textSample} ${after.tickerHints.join(' ')}`.toUpperCase().includes('BTC'), beforeTickerHints: before.tickerHints, afterTickerHints: after.tickerHints, snapshot: after };
    await page.screenshot({ path: path.join(a.output, '02-after-symbol-switch.png') });

    const marketCount = () => responses.filter((x) => /quote|history|candle|bar|stream|security|timeseries|chart|market|socket/i.test(x.url)).length;
    const hb = marketCount();
    const cp = await chartPoint(page);
    if (cp) {
      await page.mouse.move(cp.x, cp.y);
      for (let i = 0; i < 6; i += 1) {
        await page.keyboard.down('Shift');
        await page.mouse.wheel({ deltaX: -900, deltaY: 0 });
        await page.keyboard.up('Shift');
        await sleep(450);
      }
    }
    await sleep(7000);
    r.stages.historyScroll = { newMarketRequests: Math.max(0, marketCount() - hb), snapshot: await snap(page) };
    await page.screenshot({ path: path.join(a.output, '03-history-scroll.png') });

    await cdp.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0, connectionType: 'none' });
    await sleep(cfg.offlineMs);
    const offlineSnapshot = await snap(page);
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 80, downloadThroughput: -1, uploadThroughput: -1, connectionType: 'wifi' });
    const atOnline = frames.length;
    await sleep(cfg.reconnectWaitMs);
    r.stages.reconnect = { websocketFramesAfterOnline: Math.max(0, frames.length - atOnline), offlineSnapshot, snapshot: await snap(page) };
    await page.screenshot({ path: path.join(a.output, '04-reconnect.png') });

    const tr = Date.now();
    await page.reload({ waitUntil: 'domcontentloaded', timeout: cfg.navigationTimeoutMs });
    await sleep(cfg.reloadWaitMs);
    r.stages.reload = { elapsedMs: Date.now() - tr, snapshot: await snap(page) };
    await page.screenshot({ path: path.join(a.output, '05-reload.png') });
  } finally {
    const patterns = [/IndicatorManager/i, /ChartStore/i, /is a required field/i, /Cannot read properties of undefined/i, /Time scale or logical range is not defined/i, /fetched too much times per second/i, /failed to establish stream connection/i, /ZOrder to removed drawing/i, /failed to find logs for alert/i];
    const signatures = uniq([...consoleMessages.map((x) => x.text), ...pageErrors.map((x) => x.message)].filter((x) => patterns.some((p) => p.test(x))));
    const market = responses.filter((x) => /quote|history|candle|bar|stream|security|timeseries|chart|market|socket/i.test(x.url));
    const gaps = frames.slice(1).map((x, i) => x.at - frames[i].at).filter((x) => x >= 0);
    r.console = { messages: consoleMessages, pageErrors, signatures };
    r.network = { failedRequests: failed, httpErrors: responses.filter((x) => x.status >= 400), marketDataRequests: market.slice(-500), responses: responses.slice(-1000) };
    r.transport = { websocketConnections: sockets, websocketFramesReceived: frames.length, websocketGapP50Ms: pct(gaps, 50), websocketGapP95Ms: pct(gaps, 95), websocketGapMaxMs: gaps.length ? Math.max(...gaps) : null };
    r.stateSignals.detected = uniq(Object.values(r.stages).flatMap((x) => [x?.snapshot, x?.offlineSnapshot].filter(Boolean).flatMap((s) => s.states || [])));
    r.completedAt = iso();
    r.classification = classify(r);
    const out = path.join(a.output, 'result.json');
    fs.writeFileSync(out, JSON.stringify(r, null, 2) + '\n');
    fs.writeFileSync(path.join(a.output, 'summary.md'), md(r));
    fs.writeFileSync(path.join(a.output, 'evidence.sha256'), crypto.createHash('sha256').update(fs.readFileSync(out)).digest('hex') + '  result.json\n');
    await browser.close();
  }
}

main().catch((e) => { console.error(e.stack || e); process.exit(1); });
