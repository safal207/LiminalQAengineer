#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import process from 'node:process';

const MAX_BODY_BYTES = 1_000_000;

function parseArgs(argv) {
  const args = { input: null, tickers: [], selfTest: false };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    const next = () => {
      if (i + 1 >= argv.length) throw new Error(`missing value for ${token}`);
      i += 1;
      return argv[i];
    };
    if (token === '--input') args.input = next();
    else if (token === '--tickers') args.tickers = next().split(',').map((value) => value.trim()).filter(Boolean);
    else if (token === '--self-test') args.selfTest = true;
    else throw new Error(`unknown argument: ${token}`);
  }
  if (args.selfTest) return args;
  if (!args.input) throw new Error('--input is required');
  if (args.tickers.length < 1 || args.tickers.length > 2) throw new Error('tickers must contain 1 or 2 values');
  return args;
}

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function parseQuote(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed) || parsed[0] !== 'q' || !parsed[1] || typeof parsed[1] !== 'object') return null;
  const payload = parsed[1];
  return {
    ticker: typeof payload.c === 'string' ? payload.c : null,
    initial_snapshot: payload.init === 1 || payload.init === true,
    sequence: typeof payload.n === 'number' ? payload.n : null,
    revision: typeof payload.rev === 'number' ? payload.rev : null,
    server_timestamp: typeof payload.acc_srv_tm === 'string' ? payload.acc_srv_tm : null,
    market_timestamp: typeof payload.ltt === 'string' ? payload.ltt : null,
  };
}

function timestampNumber(value) {
  if (!value) return null;
  const normalized = value.includes('T') ? value : `${value.replace(' ', 'T')}Z`;
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function summarizePhase(phase) {
  const quotes = [];
  for (const message of phase.messages ?? []) {
    if (message.is_binary || typeof message.text !== 'string') continue;
    const quote = parseQuote(message.text);
    if (quote) quotes.push({ ...quote, offset_ms: message.offset_ms, sha256: message.sha256 });
  }

  const first = new Map();
  const last = new Map();
  const lastSequence = new Map();
  const lastRevision = new Map();
  const lastServerTime = new Map();
  const seenIncrementalSequence = new Set();
  const duplicateIncrementalSequences = [];
  const sequenceRegressions = [];
  const revisionRegressions = [];
  const serverTimeRegressions = [];

  for (const quote of quotes) {
    if (!quote.ticker) continue;
    if (!first.has(quote.ticker)) first.set(quote.ticker, quote);
    last.set(quote.ticker, quote);

    if (!quote.initial_snapshot && quote.sequence !== null) {
      const id = `${quote.ticker}:${quote.sequence}`;
      if (seenIncrementalSequence.has(id)) duplicateIncrementalSequences.push(id);
      seenIncrementalSequence.add(id);
    }

    if (quote.sequence !== null) {
      const previous = lastSequence.get(quote.ticker);
      if (previous !== undefined && quote.sequence < previous) {
        sequenceRegressions.push({ ticker: quote.ticker, previous, current: quote.sequence });
      }
      lastSequence.set(quote.ticker, quote.sequence);
    }
    if (quote.revision !== null) {
      const previous = lastRevision.get(quote.ticker);
      if (previous !== undefined && quote.revision < previous) {
        revisionRegressions.push({ ticker: quote.ticker, previous, current: quote.revision });
      }
      lastRevision.set(quote.ticker, quote.revision);
    }
    const serverTime = timestampNumber(quote.server_timestamp);
    if (serverTime !== null) {
      const previous = lastServerTime.get(quote.ticker);
      if (previous !== undefined && serverTime < previous) {
        serverTimeRegressions.push({ ticker: quote.ticker, previous, current: serverTime });
      }
      lastServerTime.set(quote.ticker, serverTime);
    }
  }

  const compact = (quote) => quote ? {
    ticker: quote.ticker,
    initial_snapshot: quote.initial_snapshot,
    sequence: quote.sequence,
    revision: quote.revision,
    server_timestamp: quote.server_timestamp,
    market_timestamp: quote.market_timestamp,
    offset_ms: quote.offset_ms,
    sha256: quote.sha256,
  } : null;

  return {
    phase: phase.phase,
    quote_count: quotes.length,
    first_by_ticker: Object.fromEntries([...first].map(([ticker, quote]) => [ticker, compact(quote)])),
    last_by_ticker: Object.fromEntries([...last].map(([ticker, quote]) => [ticker, compact(quote)])),
    duplicate_incremental_sequences: duplicateIncrementalSequences,
    sequence_regressions: sequenceRegressions,
    revision_regressions: revisionRegressions,
    server_time_regressions: serverTimeRegressions,
  };
}

async function boundedFetch(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch(url, {
      headers: {
        accept: 'application/json,text/plain;q=0.9,*/*;q=0.1',
        'user-agent': 'LiminalQA-bounded-public-quote-audit/1.1',
      },
      redirect: 'manual',
      signal: controller.signal,
    });
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length > MAX_BODY_BYTES) throw new Error(`response exceeded ${MAX_BODY_BYTES} bytes`);
    const text = bytes.toString('utf8');
    let parsed = null;
    let parseError = null;
    try { parsed = JSON.parse(text); } catch (error) { parseError = error.message; }
    return {
      request: { method: 'GET', origin: new URL(url).origin, path: new URL(url).pathname, delimiter_encoding: 'literal-plus' },
      response: {
        status: response.status,
        size_bytes: bytes.length,
        sha256: sha256(bytes),
        json_parse_error: parseError,
        array_length: Array.isArray(parsed) ? parsed.length : null,
        snippet: text.slice(0, 600),
      },
      error: null,
    };
  } catch (error) {
    return { request: { method: 'GET', origin: new URL(url).origin, path: new URL(url).pathname, delimiter_encoding: 'literal-plus' }, response: null, error: `${error.name}: ${error.message}` };
  } finally {
    clearTimeout(timeout);
  }
}

function adjudicate(result, phases) {
  const [before, after] = phases;
  const regressions = [];
  const continuity = [];
  for (const ticker of result.config.tickers) {
    const previous = before.last_by_ticker[ticker];
    const current = after.first_by_ticker[ticker];
    if (!previous || !current) continue;
    if (previous.sequence !== null && current.sequence !== null && current.sequence < previous.sequence) {
      regressions.push({ ticker, field: 'sequence', previous: previous.sequence, current: current.sequence });
    }
    if (previous.revision !== null && current.revision !== null && current.revision < previous.revision) {
      regressions.push({ ticker, field: 'revision', previous: previous.revision, current: current.revision });
    }
    continuity.push({
      ticker,
      before_sequence: previous.sequence,
      reconnect_sequence: current.sequence,
      before_revision: previous.revision,
      reconnect_revision: current.revision,
      reconnect_initial_snapshot: current.initial_snapshot,
      same_or_newer_sequence: previous.sequence === null || current.sequence === null || current.sequence >= previous.sequence,
      same_or_newer_revision: previous.revision === null || current.revision === null || current.revision >= previous.revision,
    });
  }

  const duplicateCount = phases.reduce((sum, phase) => sum + phase.duplicate_incremental_sequences.length, 0);
  const localRegressionCount = phases.reduce((sum, phase) => sum + phase.sequence_regressions.length + phase.revision_regressions.length + phase.server_time_regressions.length, 0);
  const initialWorked = result.adjudication.ws_quotes_before_drop === true;
  const resumed = result.adjudication.ws_quotes_after_resubscribe === true;
  const reconnectDefectReproduced = initialWorked && (!resumed || regressions.length > 0 || duplicateCount > 0 || localRegressionCount > 0);

  return {
    reconnect_defect_reproduced: reconnectDefectReproduced,
    initial_quote_flow_worked: initialWorked,
    quote_flow_resumed_after_reconnect: resumed,
    reconnect_continuity: continuity,
    reconnect_regressions: regressions,
    duplicate_incremental_sequence_count: duplicateCount,
    within_phase_regression_count: localRegressionCount,
    verdict: reconnectDefectReproduced ? 'DEFECT_CANDIDATE' : (initialWorked && resumed ? 'NOT_REPRODUCED' : 'INCONCLUSIVE'),
    claim_boundary: 'This single-client, two-ticker public run tests user-visible reconnect/resubscribe continuity. It cannot prove or disprove server-side zombie connection retention without server metrics or authenticated session instrumentation.',
  };
}

function selfTest() {
  const phase = {
    phase: 'test',
    messages: [
      { is_binary: false, offset_ms: 1, sha256: 'a', text: '["q",{"c":"AAPL.US","init":1,"n":10,"rev":20,"acc_srv_tm":"2026-01-01 00:00:00.000"}]' },
      { is_binary: false, offset_ms: 2, sha256: 'b', text: '["q",{"c":"AAPL.US","init":0,"n":11,"rev":21,"acc_srv_tm":"2026-01-01 00:00:01.000"}]' },
    ],
  };
  const summary = summarizePhase(phase);
  if (summary.quote_count !== 2 || summary.sequence_regressions.length !== 0) throw new Error('phase summary failed');
  if (summary.last_by_ticker['AAPL.US'].sequence !== 11) throw new Error('last quote summary failed');
  console.log('self-test: ok');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) return selfTest();
  const result = JSON.parse(await fs.readFile(args.input, 'utf8'));
  if (!Array.isArray(result.websocket) || result.websocket.length !== 2) throw new Error('expected exactly two WebSocket phases');
  const phases = result.websocket.map(summarizePhase);
  const literalTickers = args.tickers.map((ticker) => encodeURIComponent(ticker)).join('+');
  const correctedExport = await boundedFetch(`https://tradernet.com/securities/export?tickers=${literalTickers}`);
  result.deep_analysis = {
    schema_version: 'liminalqa-tradernet-quote-reconnect-analysis-v1',
    phases,
    corrected_securities_export_probe: correctedExport,
    adjudication: adjudicate(result, phases),
  };
  await fs.writeFile(args.input, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(result.deep_analysis.adjudication, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 2;
});
