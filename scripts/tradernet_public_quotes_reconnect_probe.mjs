#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { performance } from 'node:perf_hooks';

const MAX_BODY_BYTES = 1_000_000;
const MAX_WS_MESSAGES = 200;
const MAX_WS_BYTES = 512_000;
const DEFAULT_TICKERS = ['AAPL.US', 'MSFT.US'];

function parseArgs(argv) {
  const args = {
    outputDir: null,
    tickers: DEFAULT_TICKERS,
    wsEndpoint: 'wss://wss.tradernet.com',
    phaseMs: 12_000,
    reconnectDelayMs: 1_000,
    handshakeTimeoutMs: 10_000,
    selfTest: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    const value = () => {
      if (i + 1 >= argv.length) throw new Error(`missing value for ${token}`);
      i += 1;
      return argv[i];
    };
    if (token === '--output-dir') args.outputDir = value();
    else if (token === '--tickers') args.tickers = value().split(',').map((item) => item.trim()).filter(Boolean);
    else if (token === '--ws-endpoint') args.wsEndpoint = value();
    else if (token === '--phase-ms') args.phaseMs = Number(value());
    else if (token === '--reconnect-delay-ms') args.reconnectDelayMs = Number(value());
    else if (token === '--handshake-timeout-ms') args.handshakeTimeoutMs = Number(value());
    else if (token === '--self-test') args.selfTest = true;
    else throw new Error(`unknown argument: ${token}`);
  }
  if (args.selfTest) return args;
  if (!args.outputDir) throw new Error('--output-dir is required');
  if (args.tickers.length < 1 || args.tickers.length > 2) throw new Error('tickers must contain 1 or 2 symbols');
  if (![args.phaseMs, args.reconnectDelayMs, args.handshakeTimeoutMs].every(Number.isFinite)) {
    throw new Error('duration arguments must be finite numbers');
  }
  if (args.phaseMs < 3_000 || args.phaseMs > 30_000) throw new Error('phase-ms must be between 3000 and 30000');
  if (args.reconnectDelayMs < 250 || args.reconnectDelayMs > 5_000) throw new Error('reconnect-delay-ms must be between 250 and 5000');
  if (args.handshakeTimeoutMs < 2_000 || args.handshakeTimeoutMs > 20_000) throw new Error('handshake-timeout-ms must be between 2000 and 20000');
  return args;
}

function isoNow() {
  return new Date().toISOString();
}

function sha256Bytes(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function safeHeaders(headers) {
  const allow = ['content-type', 'content-length', 'cache-control', 'date', 'server', 'x-request-id'];
  const result = {};
  for (const name of allow) {
    const value = headers.get(name);
    if (value !== null) result[name] = value;
  }
  return result;
}

async function readBoundedBody(response) {
  const chunks = [];
  let total = 0;
  const reader = response.body?.getReader();
  if (!reader) return Buffer.alloc(0);
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_BODY_BYTES) throw new Error(`response body exceeded ${MAX_BODY_BYTES} bytes`);
    chunks.push(Buffer.from(value));
  }
  return Buffer.concat(chunks);
}

function parseJsonMaybe(text) {
  try {
    return { parsed: JSON.parse(text), error: null };
  } catch (error) {
    return { parsed: null, error: error instanceof Error ? error.message : String(error) };
  }
}

function collectTickerMentions(value, found = new Set()) {
  if (typeof value === 'string') {
    if (/^[A-Z0-9./_-]{2,20}$/.test(value)) found.add(value);
    return found;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectTickerMentions(item, found);
    return found;
  }
  if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      if (['c', 'ticker', 'symbol', 't'].includes(key) && typeof item === 'string') found.add(item);
      collectTickerMentions(item, found);
    }
  }
  return found;
}

async function httpProbe({ id, url, method = 'GET', body = null, headers = {} }, expectedTickers) {
  const startedAt = isoNow();
  const start = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch(url, {
      method,
      headers: {
        'user-agent': 'LiminalQA-bounded-public-quote-audit/1.0',
        accept: 'application/json,text/plain;q=0.9,*/*;q=0.1',
        ...headers,
      },
      body,
      redirect: 'manual',
      signal: controller.signal,
    });
    const bytes = await readBoundedBody(response);
    const text = bytes.toString('utf8');
    const json = parseJsonMaybe(text);
    const mentions = json.parsed ? [...collectTickerMentions(json.parsed)].sort() : [];
    return {
      id,
      started_at: startedAt,
      completed_at: isoNow(),
      duration_ms: Number((performance.now() - start).toFixed(1)),
      request: { method, origin: new URL(url).origin, path: new URL(url).pathname },
      response: {
        status: response.status,
        status_text: response.statusText,
        headers: safeHeaders(response.headers),
        size_bytes: bytes.length,
        sha256: sha256Bytes(bytes),
        json_parse_error: json.error,
        ticker_mentions: mentions,
        expected_tickers_observed: expectedTickers.filter((ticker) => mentions.includes(ticker)),
        snippet: text.slice(0, 600),
      },
      error: null,
    };
  } catch (error) {
    return {
      id,
      started_at: startedAt,
      completed_at: isoNow(),
      duration_ms: Number((performance.now() - start).toFixed(1)),
      request: { method, origin: new URL(url).origin, path: new URL(url).pathname },
      response: null,
      error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
    };
  } finally {
    clearTimeout(timeout);
  }
}

function extractQuoteEvent(parsed) {
  let event = null;
  let payload = null;
  if (Array.isArray(parsed) && typeof parsed[0] === 'string') {
    [event, payload] = parsed;
  } else if (parsed && typeof parsed === 'object') {
    event = parsed.event ?? parsed.type ?? parsed.e ?? null;
    payload = parsed.data ?? parsed.payload ?? parsed;
  }
  if (event !== 'q' && event !== 'quotes' && event !== 'quote') return null;
  const ticker = payload?.c ?? payload?.ticker ?? payload?.symbol ?? null;
  const timestamp = payload?.timestamp ?? payload?.time ?? payload?.ts ?? payload?.lt ?? payload?.t ?? null;
  return { event, ticker: typeof ticker === 'string' ? ticker : null, timestamp };
}

function normalizeTimestamp(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

async function websocketPhase({ endpoint, tickers, phase, durationMs, handshakeTimeoutMs, terminateAtEnd }) {
  const { default: WebSocket } = await import('ws');
  const startedAt = isoNow();
  const startedMono = performance.now();
  const messages = [];
  const quoteEvents = [];
  const errors = [];
  let receivedBytes = 0;
  let openAtMs = null;
  let subscriptionSentAtMs = null;
  let closeInfo = null;
  let truncated = false;

  await new Promise((resolve) => {
    const ws = new WebSocket(endpoint, {
      handshakeTimeout: handshakeTimeoutMs,
      headers: { 'user-agent': 'LiminalQA-bounded-public-quote-audit/1.0' },
    });
    let resolved = false;
    const finish = () => {
      if (resolved) return;
      resolved = true;
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      if (terminateAtEnd && ws.readyState === WebSocket.OPEN) ws.terminate();
      else if (ws.readyState === WebSocket.OPEN) ws.close(1000, 'bounded audit complete');
      else if (ws.readyState !== WebSocket.CLOSED) ws.terminate();
      setTimeout(finish, 250);
    }, durationMs);

    ws.on('open', () => {
      openAtMs = Number((performance.now() - startedMono).toFixed(1));
      const subscription = JSON.stringify(['quotes', tickers]);
      ws.send(subscription, (error) => {
        if (error) errors.push(`send: ${error.message}`);
        else subscriptionSentAtMs = Number((performance.now() - startedMono).toFixed(1));
      });
    });

    ws.on('message', (data, isBinary) => {
      const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
      receivedBytes += buffer.length;
      if (messages.length >= MAX_WS_MESSAGES || receivedBytes > MAX_WS_BYTES) {
        truncated = true;
        return;
      }
      const text = isBinary ? buffer.toString('base64') : buffer.toString('utf8');
      const record = {
        offset_ms: Number((performance.now() - startedMono).toFixed(1)),
        is_binary: isBinary,
        size_bytes: buffer.length,
        sha256: sha256Bytes(buffer),
        text: text.slice(0, 2_000),
      };
      if (!isBinary) {
        const parsed = parseJsonMaybe(text);
        record.json_parse_error = parsed.error;
        if (parsed.parsed !== null) {
          const quote = extractQuoteEvent(parsed.parsed);
          if (quote) {
            record.quote = quote;
            quoteEvents.push({ ...quote, offset_ms: record.offset_ms, sha256: record.sha256 });
          }
        }
      }
      messages.push(record);
    });

    ws.on('unexpected-response', (_request, response) => {
      errors.push(`unexpected-response: HTTP ${response.statusCode}`);
      finish();
    });
    ws.on('error', (error) => errors.push(`${error.name}: ${error.message}`));
    ws.on('close', (code, reason) => {
      closeInfo = { code, reason: reason.toString('utf8') };
      finish();
    });
  });

  const firstQuoteAtMs = quoteEvents.length ? quoteEvents[0].offset_ms : null;
  const exactDuplicateHashes = quoteEvents.length - new Set(quoteEvents.map((item) => item.sha256)).size;
  const outOfOrder = [];
  const lastByTicker = new Map();
  for (const quote of quoteEvents) {
    const numeric = normalizeTimestamp(quote.timestamp);
    if (!quote.ticker || numeric === null) continue;
    const previous = lastByTicker.get(quote.ticker);
    if (previous !== undefined && numeric < previous) outOfOrder.push({ ticker: quote.ticker, previous, current: numeric });
    lastByTicker.set(quote.ticker, numeric);
  }
  return {
    phase,
    endpoint,
    started_at: startedAt,
    completed_at: isoNow(),
    duration_ms: Number((performance.now() - startedMono).toFixed(1)),
    open_at_ms: openAtMs,
    subscription_sent_at_ms: subscriptionSentAtMs,
    first_quote_at_ms: firstQuoteAtMs,
    message_count: messages.length,
    received_bytes: receivedBytes,
    truncated,
    quote_event_count: quoteEvents.length,
    quote_tickers: [...new Set(quoteEvents.map((item) => item.ticker).filter(Boolean))].sort(),
    exact_duplicate_quote_hashes: exactDuplicateHashes,
    out_of_order_quote_timestamps: outOfOrder,
    close: closeInfo,
    errors,
    messages,
  };
}

function adjudicate(httpResults, wsPhases, tickers) {
  const httpQuoteSuccess = httpResults.some((result) =>
    result.response?.status === 200 && result.response.expected_tickers_observed.length > 0,
  );
  const [before, after] = wsPhases;
  const wsConnectedBefore = before?.open_at_ms !== null;
  const wsConnectedAfter = after?.open_at_ms !== null;
  const quotesBefore = (before?.quote_event_count ?? 0) > 0;
  const quotesAfter = (after?.quote_event_count ?? 0) > 0;
  const resumedAfterReconnect = quotesBefore && quotesAfter;
  const findings = [];
  if (!httpQuoteSuccess) findings.push({ level: 'SIGNAL', code: 'HTTP_QUOTES_NOT_CONFIRMED', detail: 'No bounded HTTP probe returned a parseable response containing an expected ticker.' });
  if (!wsConnectedBefore) findings.push({ level: 'SIGNAL', code: 'WS_INITIAL_CONNECT_NOT_CONFIRMED', detail: 'The documented/known public WebSocket endpoint did not reach OPEN without credentials.' });
  if (wsConnectedBefore && !quotesBefore) findings.push({ level: 'INCONCLUSIVE', code: 'WS_NO_QUOTES_BEFORE_DROP', detail: 'Connection opened and subscription was sent, but no quote event was observed in the bounded window.' });
  if (quotesBefore && !wsConnectedAfter) findings.push({ level: 'DEFECT_CANDIDATE', code: 'WS_RECONNECT_FAILED', detail: 'Initial quote flow worked, but the single reconnect did not open.' });
  if (quotesBefore && wsConnectedAfter && !quotesAfter) findings.push({ level: 'DEFECT_CANDIDATE', code: 'WS_RESUBSCRIBE_DID_NOT_RESUME', detail: 'Initial quotes were observed, reconnect opened, resubscribe was sent, but quotes did not resume in the same bounded window.' });
  for (const phase of wsPhases) {
    if ((phase?.out_of_order_quote_timestamps?.length ?? 0) > 0) findings.push({ level: 'DEFECT_CANDIDATE', code: 'WS_OUT_OF_ORDER_QUOTES', detail: `${phase.phase}: quote timestamps moved backwards.` });
  }
  return {
    scope: 'public unauthenticated read-only; at most two tickers; one active WebSocket; one controlled disconnect and reconnect',
    tickers,
    http_quote_success: httpQuoteSuccess,
    ws_connected_before_drop: wsConnectedBefore,
    ws_quotes_before_drop: quotesBefore,
    ws_connected_after_drop: wsConnectedAfter,
    ws_quotes_after_resubscribe: quotesAfter,
    ws_resumed_after_reconnect: resumedAfterReconnect,
    findings,
    claim_boundary: 'A missing quote in a short window is inconclusive when the market is closed or the endpoint requires authorization. A defect candidate requires an initially working quote flow followed by a failed reconnect/resubscribe under the same run.',
  };
}

async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function markdownSummary(result) {
  const a = result.adjudication;
  const lines = [
    '# Tradernet public quote and reconnect probe',
    '',
    `- Started: ${result.started_at}`,
    `- Completed: ${result.completed_at}`,
    `- Tickers: ${result.config.tickers.join(', ')}`,
    `- WebSocket: ${result.config.ws_endpoint}`,
    '',
    '## Result',
    '',
    `- HTTP quote confirmed: **${a.http_quote_success}**`,
    `- WS opened before drop: **${a.ws_connected_before_drop}**`,
    `- Quotes before drop: **${a.ws_quotes_before_drop}**`,
    `- WS opened after drop: **${a.ws_connected_after_drop}**`,
    `- Quotes after resubscribe: **${a.ws_quotes_after_resubscribe}**`,
    `- Resumed after reconnect: **${a.ws_resumed_after_reconnect}**`,
    '',
    '## Findings',
    '',
  ];
  if (!a.findings.length) lines.push('- No bounded reconnect defect reproduced.');
  for (const finding of a.findings) lines.push(`- **${finding.level} / ${finding.code}:** ${finding.detail}`);
  lines.push('', '## Boundary', '', a.claim_boundary, '');
  return lines.join('\n');
}

function selfTest() {
  const quote = extractQuoteEvent(['q', { c: 'AAPL.US', p: 123.4, t: 10 }]);
  if (quote?.ticker !== 'AAPL.US' || quote.timestamp !== 10) throw new Error('array quote parsing failed');
  const objectQuote = extractQuoteEvent({ event: 'q', data: { c: 'MSFT.US', timestamp: '2026-01-01T00:00:00Z' } });
  if (objectQuote?.ticker !== 'MSFT.US') throw new Error('object quote parsing failed');
  if (extractQuoteEvent(['orderBook', { c: 'AAPL.US' }]) !== null) throw new Error('non-quote event accepted');
  const mentions = [...collectTickerMentions({ q: [{ c: 'AAPL.US' }, { ticker: 'MSFT.US' }] })];
  if (!mentions.includes('AAPL.US') || !mentions.includes('MSFT.US')) throw new Error('ticker collection failed');
  console.log('self-test: ok');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) {
    selfTest();
    return;
  }
  const outputDir = path.resolve(args.outputDir);
  await fs.mkdir(outputDir, { recursive: true });
  const startedAt = isoNow();
  const q = JSON.stringify({ cmd: 'getStockQuotesJson', params: { tickers: args.tickers } });
  const encoded = new URLSearchParams({ q }).toString();
  const plusTickers = args.tickers.join('+');
  const httpSpecs = [
    {
      id: 'post-tradernet-com-api',
      url: 'https://tradernet.com/api/',
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded;charset=UTF-8' },
      body: encoded,
    },
    {
      id: 'get-tradernet-ru-api',
      url: `https://tradernet.ru/api/?${encoded}`,
    },
    {
      id: 'get-securities-export',
      url: `https://tradernet.com/securities/export?tickers=${encodeURIComponent(plusTickers)}`,
    },
  ];
  const httpResults = [];
  for (const spec of httpSpecs) httpResults.push(await httpProbe(spec, args.tickers));

  const before = await websocketPhase({
    endpoint: args.wsEndpoint,
    tickers: args.tickers,
    phase: 'before-controlled-drop',
    durationMs: args.phaseMs,
    handshakeTimeoutMs: args.handshakeTimeoutMs,
    terminateAtEnd: true,
  });
  await new Promise((resolve) => setTimeout(resolve, args.reconnectDelayMs));
  const after = await websocketPhase({
    endpoint: args.wsEndpoint,
    tickers: args.tickers,
    phase: 'after-reconnect-resubscribe',
    durationMs: args.phaseMs,
    handshakeTimeoutMs: args.handshakeTimeoutMs,
    terminateAtEnd: false,
  });

  const result = {
    schema_version: 'liminalqa-tradernet-public-quotes-reconnect-v1',
    started_at: startedAt,
    completed_at: isoNow(),
    config: {
      tickers: args.tickers,
      ws_endpoint: args.wsEndpoint,
      phase_ms: args.phaseMs,
      reconnect_delay_ms: args.reconnectDelayMs,
      handshake_timeout_ms: args.handshakeTimeoutMs,
      maximum_active_connections: 1,
      controlled_disconnects: 1,
    },
    http: httpResults,
    websocket: [before, after],
    adjudication: adjudicate(httpResults, [before, after], args.tickers),
  };
  await writeJson(path.join(outputDir, 'tradernet-public-quotes-reconnect.json'), result);
  await fs.writeFile(path.join(outputDir, 'tradernet-public-quotes-reconnect.md'), markdownSummary(result), 'utf8');
  console.log(JSON.stringify(result.adjudication, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 2;
});
