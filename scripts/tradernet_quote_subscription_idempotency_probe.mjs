#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { performance } from 'node:perf_hooks';

const MAX_MESSAGES = 250;
const MAX_BYTES = 600_000;

function parseArgs(argv) {
  const args = {
    outputDir: null,
    tickers: [],
    endpoint: 'wss://wss.tradernet.com',
    repeatAfterMs: 4_000,
    observationMs: 12_000,
    handshakeTimeoutMs: 10_000,
    selfTest: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    const next = () => {
      if (index + 1 >= argv.length) throw new Error(`missing value for ${token}`);
      index += 1;
      return argv[index];
    };
    if (token === '--output-dir') args.outputDir = next();
    else if (token === '--tickers') args.tickers = next().split(',').map((value) => value.trim()).filter(Boolean);
    else if (token === '--endpoint') args.endpoint = next();
    else if (token === '--repeat-after-ms') args.repeatAfterMs = Number(next());
    else if (token === '--observation-ms') args.observationMs = Number(next());
    else if (token === '--handshake-timeout-ms') args.handshakeTimeoutMs = Number(next());
    else if (token === '--self-test') args.selfTest = true;
    else throw new Error(`unknown argument: ${token}`);
  }
  if (args.selfTest) return args;
  if (!args.outputDir) throw new Error('--output-dir is required');
  if (args.tickers.length < 1 || args.tickers.length > 2) throw new Error('tickers must contain 1 or 2 values');
  if (!Number.isFinite(args.repeatAfterMs) || args.repeatAfterMs < 2_000 || args.repeatAfterMs > 8_000) throw new Error('repeat-after-ms out of bounds');
  if (!Number.isFinite(args.observationMs) || args.observationMs < args.repeatAfterMs + 3_000 || args.observationMs > 20_000) throw new Error('observation-ms out of bounds');
  if (!Number.isFinite(args.handshakeTimeoutMs) || args.handshakeTimeoutMs < 2_000 || args.handshakeTimeoutMs > 20_000) throw new Error('handshake timeout out of bounds');
  return args;
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function parseQuote(text) {
  let parsed;
  try { parsed = JSON.parse(text); } catch { return null; }
  if (!Array.isArray(parsed) || parsed[0] !== 'q' || !parsed[1] || typeof parsed[1] !== 'object') return null;
  const payload = parsed[1];
  return {
    ticker: typeof payload.c === 'string' ? payload.c : null,
    initial_snapshot: payload.init === 1 || payload.init === true,
    sequence: Number.isFinite(payload.n) ? payload.n : null,
    revision: Number.isFinite(payload.rev) ? payload.rev : null,
    market_timestamp: typeof payload.ltt === 'string' ? payload.ltt : null,
  };
}

function adjudicate(records, repeatSentAtMs, tickers) {
  const quotes = records.filter((record) => record.quote).map((record) => ({ ...record.quote, offset_ms: record.offset_ms, sha256: record.sha256 }));
  const before = quotes.filter((quote) => quote.offset_ms < repeatSentAtMs);
  const after = quotes.filter((quote) => quote.offset_ms >= repeatSentAtMs);
  const seenIncremental = new Set();
  const duplicateIncremental = [];
  for (const quote of quotes) {
    if (quote.initial_snapshot || quote.sequence === null || !quote.ticker) continue;
    const key = `${quote.ticker}:${quote.sequence}`;
    if (seenIncremental.has(key)) duplicateIncremental.push(key);
    seenIncremental.add(key);
  }
  const initialSnapshotsAfterRepeat = after.filter((quote) => quote.initial_snapshot).map((quote) => ({ ticker: quote.ticker, sequence: quote.sequence, revision: quote.revision, offset_ms: quote.offset_ms }));
  const beforeTickers = [...new Set(before.map((quote) => quote.ticker).filter(Boolean))].sort();
  const afterTickers = [...new Set(after.map((quote) => quote.ticker).filter(Boolean))].sort();
  const flowBefore = tickers.every((ticker) => beforeTickers.includes(ticker));
  const flowAfter = tickers.every((ticker) => afterTickers.includes(ticker));
  const defectCandidate = flowBefore && duplicateIncremental.length > 0;
  return {
    verdict: defectCandidate ? 'DEFECT_CANDIDATE' : (flowBefore && flowAfter ? 'NOT_REPRODUCED' : 'INCONCLUSIVE'),
    quote_count_before_repeat: before.length,
    quote_count_after_repeat: after.length,
    quote_tickers_before_repeat: beforeTickers,
    quote_tickers_after_repeat: afterTickers,
    duplicate_incremental_sequences: duplicateIncremental,
    initial_snapshots_after_repeat: initialSnapshotsAfterRepeat,
    invariant: 'Sending the same subscription once more on the same connection must not create duplicate incremental delivery for the same ticker and sequence.',
    claim_boundary: 'This checks one repeated identical subscription on one public demo connection. It is not a mass-subscription, concurrency or server resource-leak test.',
  };
}

function selfTest() {
  const records = [
    { offset_ms: 100, sha256: 'a', quote: { ticker: 'AAPL.US', initial_snapshot: false, sequence: 1, revision: 1 } },
    { offset_ms: 5000, sha256: 'b', quote: { ticker: 'AAPL.US', initial_snapshot: false, sequence: 1, revision: 1 } },
  ];
  const result = adjudicate(records, 4000, ['AAPL.US']);
  if (result.verdict !== 'DEFECT_CANDIDATE') throw new Error('duplicate sequence self-test failed');
  console.log('self-test: ok');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) return selfTest();
  const { default: WebSocket } = await import('ws');
  const outputDir = path.resolve(args.outputDir);
  await fs.mkdir(outputDir, { recursive: true });
  const startedAt = new Date().toISOString();
  const startedMono = performance.now();
  const records = [];
  const errors = [];
  let receivedBytes = 0;
  let openAtMs = null;
  let firstSubscriptionSentAtMs = null;
  let repeatSubscriptionSentAtMs = null;
  let close = null;
  let truncated = false;

  await new Promise((resolve) => {
    const socket = new WebSocket(args.endpoint, {
      handshakeTimeout: args.handshakeTimeoutMs,
      headers: { 'user-agent': 'LiminalQA-bounded-subscription-idempotency-audit/1.0' },
    });
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(observationTimer);
      clearTimeout(repeatTimer);
      resolve();
    };
    const payload = JSON.stringify(['quotes', args.tickers]);
    const repeatTimer = setTimeout(() => {
      if (socket.readyState !== WebSocket.OPEN) return;
      socket.send(payload, (error) => {
        if (error) errors.push(`repeat-send: ${error.message}`);
        else repeatSubscriptionSentAtMs = Number((performance.now() - startedMono).toFixed(1));
      });
    }, args.repeatAfterMs);
    const observationTimer = setTimeout(() => {
      if (socket.readyState === WebSocket.OPEN) socket.close(1000, 'bounded idempotency audit complete');
      else if (socket.readyState !== WebSocket.CLOSED) socket.terminate();
      setTimeout(finish, 250);
    }, args.observationMs);

    socket.on('open', () => {
      openAtMs = Number((performance.now() - startedMono).toFixed(1));
      socket.send(payload, (error) => {
        if (error) errors.push(`initial-send: ${error.message}`);
        else firstSubscriptionSentAtMs = Number((performance.now() - startedMono).toFixed(1));
      });
    });
    socket.on('message', (data, isBinary) => {
      const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
      receivedBytes += buffer.length;
      if (records.length >= MAX_MESSAGES || receivedBytes > MAX_BYTES) {
        truncated = true;
        return;
      }
      const text = isBinary ? buffer.toString('base64') : buffer.toString('utf8');
      records.push({
        offset_ms: Number((performance.now() - startedMono).toFixed(1)),
        is_binary: isBinary,
        size_bytes: buffer.length,
        sha256: sha256(buffer),
        text: text.slice(0, 2000),
        quote: isBinary ? null : parseQuote(text),
      });
    });
    socket.on('error', (error) => errors.push(`${error.name}: ${error.message}`));
    socket.on('unexpected-response', (_request, response) => {
      errors.push(`unexpected-response: HTTP ${response.statusCode}`);
      finish();
    });
    socket.on('close', (code, reason) => {
      close = { code, reason: reason.toString('utf8') };
      finish();
    });
  });

  const adjudication = adjudicate(records, repeatSubscriptionSentAtMs ?? Number.POSITIVE_INFINITY, args.tickers);
  const result = {
    schema_version: 'liminalqa-tradernet-public-subscription-idempotency-v1',
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    config: {
      endpoint: args.endpoint,
      tickers: args.tickers,
      repeat_after_ms: args.repeatAfterMs,
      observation_ms: args.observationMs,
      maximum_active_connections: 1,
      subscription_messages_sent: repeatSubscriptionSentAtMs === null ? 1 : 2,
    },
    lifecycle: {
      open_at_ms: openAtMs,
      first_subscription_sent_at_ms: firstSubscriptionSentAtMs,
      repeat_subscription_sent_at_ms: repeatSubscriptionSentAtMs,
      close,
      errors,
      received_bytes: receivedBytes,
      message_count: records.length,
      truncated,
    },
    adjudication,
    messages: records,
  };
  await fs.writeFile(path.join(outputDir, 'tradernet-quote-subscription-idempotency.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(adjudication, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 2;
});
