#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

function parseArgs(argv) {
  const args = { reconnectInput: null, idempotencyInput: null, contract: null, outputDir: null, selfTest: false };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    const next = () => {
      if (index + 1 >= argv.length) throw new Error(`missing value for ${token}`);
      index += 1;
      return argv[index];
    };
    if (token === '--reconnect-input') args.reconnectInput = next();
    else if (token === '--idempotency-input') args.idempotencyInput = next();
    else if (token === '--contract') args.contract = next();
    else if (token === '--output-dir') args.outputDir = next();
    else if (token === '--self-test') args.selfTest = true;
    else throw new Error(`unknown argument: ${token}`);
  }
  if (args.selfTest) return args;
  for (const key of ['reconnectInput', 'idempotencyInput', 'contract', 'outputDir']) {
    if (!args[key]) throw new Error(`--${key.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)} is required`);
  }
  return args;
}

function parseTimestamp(value) {
  if (typeof value !== 'string' || value.length < 8) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseQuoteMessage(message, source) {
  if (message?.is_binary || typeof message?.text !== 'string') return null;
  let parsed;
  try { parsed = JSON.parse(message.text); } catch { return null; }
  if (!Array.isArray(parsed) || parsed[0] !== 'q' || !parsed[1] || typeof parsed[1] !== 'object') return null;
  const payload = parsed[1];
  if (typeof payload.c !== 'string') return null;
  return {
    source,
    ticker: payload.c,
    payload,
    sequence: Number.isFinite(payload.n) ? payload.n : null,
    revision: Number.isFinite(payload.rev) ? payload.rev : null,
    initialSnapshot: payload.init === 1 || payload.init === true,
    marketTimestamp: typeof payload.ltt === 'string' ? payload.ltt : null,
    marketTimestampMs: parseTimestamp(payload.ltt),
    ltp: Number.isFinite(payload.ltp) ? payload.ltp : null,
    lts: Number.isFinite(payload.lts) ? payload.lts : null,
    offsetMs: Number.isFinite(message.offset_ms) ? message.offset_ms : null,
    sha256: typeof message.sha256 === 'string' ? message.sha256 : null,
  };
}

function hasProvenance(payload, fields) {
  const keys = new Set(Object.keys(payload).map((key) => key.toLowerCase()));
  return fields.some((field) => keys.has(field.toLowerCase()));
}

function nonDecreasing(previous, current) {
  const sequenceOk = previous.sequence === null || current.sequence === null || current.sequence >= previous.sequence;
  const revisionOk = previous.revision === null || current.revision === null || current.revision >= previous.revision;
  return sequenceOk && revisionOk;
}

function cloneState(state) {
  return state ? { ...state, payload: { ...state.payload } } : null;
}

function mergeState(previous, quote, suppressedFields = []) {
  const blocked = new Set(suppressedFields);
  const payload = { ...(previous?.payload ?? {}) };
  for (const [key, value] of Object.entries(quote.payload)) {
    if (!blocked.has(key)) payload[key] = value;
  }
  return {
    ticker: quote.ticker,
    payload,
    sequence: blocked.has('n') ? previous?.sequence ?? null : quote.sequence ?? previous?.sequence ?? null,
    revision: blocked.has('rev') ? previous?.revision ?? null : quote.revision ?? previous?.revision ?? null,
    marketTimestamp: blocked.has('ltt') ? previous?.marketTimestamp ?? null : quote.marketTimestamp ?? previous?.marketTimestamp ?? null,
    marketTimestampMs: blocked.has('ltt') ? previous?.marketTimestampMs ?? null : quote.marketTimestampMs ?? previous?.marketTimestampMs ?? null,
    ltp: blocked.has('ltp') ? previous?.ltp ?? null : quote.ltp ?? previous?.ltp ?? null,
    lts: blocked.has('lts') ? previous?.lts ?? null : quote.lts ?? previous?.lts ?? null,
    initialSnapshot: quote.initialSnapshot,
    source: quote.source,
    sha256: quote.sha256,
  };
}

function replayQuotes(quotes, contract) {
  const thresholdMs = contract.rules.material_market_time_regression_seconds * 1000;
  const provenanceFields = contract.rules.provenance_fields;
  const timeSensitive = contract.rules.time_sensitive_fields;
  const naive = new Map();
  const guarded = new Map();
  const rollbacks = [];
  const rejectedRegressions = [];

  for (const quote of quotes) {
    const previousNaive = naive.get(quote.ticker) ?? null;
    const previousGuarded = guarded.get(quote.ticker) ?? null;
    if (previousNaive && !nonDecreasing(previousNaive, quote)) {
      rejectedRegressions.push({ ticker: quote.ticker, source: quote.source, sequence: quote.sequence, revision: quote.revision });
      continue;
    }

    const materialRollback = previousNaive !== null
      && previousNaive.marketTimestampMs !== null
      && quote.marketTimestampMs !== null
      && quote.marketTimestampMs < previousNaive.marketTimestampMs - thresholdMs;
    const provenancePresent = hasProvenance(quote.payload, provenanceFields);
    const priceChanged = materialRollback
      && previousNaive !== null
      && quote.ltp !== null
      && previousNaive.ltp !== null
      && quote.ltp !== previousNaive.ltp;
    const sizeChanged = materialRollback
      && previousNaive !== null
      && quote.lts !== null
      && previousNaive.lts !== null
      && quote.lts !== previousNaive.lts;

    if (materialRollback) {
      rollbacks.push({
        ticker: quote.ticker,
        source: quote.source,
        initial_snapshot: quote.initialSnapshot,
        sequence: { previous: previousNaive.sequence, current: quote.sequence },
        revision: { previous: previousNaive.revision, current: quote.revision },
        market_time: { previous: previousNaive.marketTimestamp, current: quote.marketTimestamp },
        delta_seconds: (quote.marketTimestampMs - previousNaive.marketTimestampMs) / 1000,
        ltp: { previous: previousNaive.ltp, current: quote.ltp, changed: priceChanged },
        lts: { previous: previousNaive.lts, current: quote.lts, changed: sizeChanged },
        provenance_present: provenancePresent,
        payload_fields: Object.keys(quote.payload).sort(),
        sha256: quote.sha256,
      });
    }

    naive.set(quote.ticker, mergeState(previousNaive, quote));
    const suppress = materialRollback && !provenancePresent ? timeSensitive : [];
    guarded.set(quote.ticker, mergeState(previousGuarded, quote, suppress));
  }

  return {
    rollbacks,
    rejected_sequence_or_revision_regressions: rejectedRegressions,
    naive_final_state: Object.fromEntries([...naive.entries()].map(([ticker, state]) => [ticker, cloneState(state)])),
    guarded_final_state: Object.fromEntries([...guarded.entries()].map(([ticker, state]) => [ticker, cloneState(state)])),
    guarded_suppressed_rollback_count: rollbacks.filter((item) => !item.provenance_present).length,
  };
}

function reconnectQuotes(input) {
  const output = [];
  for (const phase of input.websocket ?? []) {
    for (const message of phase.messages ?? []) {
      const quote = parseQuoteMessage(message, `reconnect:${phase.phase}`);
      if (quote) output.push(quote);
    }
  }
  return output;
}

function idempotencyQuotes(input) {
  const repeatAt = input.lifecycle?.repeat_subscription_sent_at_ms;
  const quotes = [];
  for (const message of input.messages ?? []) {
    const side = Number.isFinite(repeatAt) && Number.isFinite(message.offset_ms) && message.offset_ms >= repeatAt ? 'after-repeat' : 'before-repeat';
    const quote = parseQuoteMessage(message, `idempotency:${side}`);
    if (quote) quotes.push(quote);
  }
  return { repeatAt, quotes };
}

function analyzeRepeatedSnapshots(input, contract) {
  const { repeatAt, quotes } = idempotencyQuotes(input);
  const state = new Map();
  const snapshots = [];
  for (const quote of quotes) {
    const previous = state.get(quote.ticker) ?? null;
    const afterRepeat = quote.source.endsWith('after-repeat');
    if (afterRepeat && quote.initialSnapshot) {
      const sequenceOlder = previous !== null
        && previous.sequence !== null
        && quote.sequence !== null
        && quote.sequence < previous.sequence;
      const revisionOlder = previous !== null
        && previous.revision !== null
        && quote.revision !== null
        && quote.revision < previous.revision;
      const timeOlder = previous !== null
        && previous.marketTimestampMs !== null
        && quote.marketTimestampMs !== null
        && quote.marketTimestampMs < previous.marketTimestampMs - contract.rules.material_market_time_regression_seconds * 1000;
      const priceChanged = previous !== null
        && previous.ltp !== null
        && quote.ltp !== null
        && previous.ltp !== quote.ltp;
      snapshots.push({
        ticker: quote.ticker,
        offset_ms: quote.offsetMs,
        sequence: { previous: previous?.sequence ?? null, current: quote.sequence, older: sequenceOlder },
        revision: { previous: previous?.revision ?? null, current: quote.revision, older: revisionOlder },
        market_time: { previous: previous?.marketTimestamp ?? null, current: quote.marketTimestamp, older: timeOlder },
        ltp: { previous: previous?.ltp ?? null, current: quote.ltp, changed: priceChanged },
        stale_reinitialization: sequenceOlder || revisionOlder || timeOlder,
        sha256: quote.sha256,
      });
    }
    if (!previous || nonDecreasing(previous, quote)) state.set(quote.ticker, mergeState(previous, quote));
  }
  return {
    repeat_subscription_sent_at_ms: repeatAt ?? null,
    initial_snapshots_after_repeat: snapshots,
    snapshot_count: snapshots.length,
    stale_reinitialization_count: snapshots.filter((item) => item.stale_reinitialization).length,
  };
}

function adjudicate(reconnectReplay, snapshotAnalysis, contract) {
  const rollbacks = reconnectReplay.rollbacks;
  const affectedTickers = [...new Set(rollbacks.map((item) => item.ticker))].sort();
  const affectedPhases = [...new Set(rollbacks.map((item) => item.source))].sort();
  const noProvenance = rollbacks.filter((item) => !item.provenance_present);
  const priceRollbacks = rollbacks.filter((item) => item.ltp.changed || item.lts.changed);
  const reducerCandidate = rollbacks.length >= contract.rules.minimum_rollbacks_for_candidate
    && affectedTickers.length >= contract.rules.minimum_affected_tickers
    && affectedPhases.length >= contract.rules.minimum_affected_connection_phases
    && reconnectReplay.guarded_suppressed_rollback_count === noProvenance.length;

  return {
    overall_verdict: reducerCandidate ? 'DEFECT_CANDIDATE' : (rollbacks.length ? 'SIGNAL' : 'NOT_OBSERVED'),
    findings: {
      'TRD-RED-001': {
        state: reducerCandidate ? 'CONFIRMED_DEFECT_CANDIDATE' : (rollbacks.length ? 'SIGNAL' : 'NOT_OBSERVED'),
        naive_visible_time_rollback_count: rollbacks.length,
        guarded_suppressed_rollback_count: reconnectReplay.guarded_suppressed_rollback_count,
        affected_tickers: affectedTickers,
        affected_connection_phases: affectedPhases,
      },
      'TRD-RED-002': {
        state: priceRollbacks.length ? 'DEFECT_CANDIDATE' : 'NOT_OBSERVED',
        backward_time_updates_with_changed_ltp_or_lts: priceRollbacks.length,
      },
      'TRD-RED-003': {
        state: snapshotAnalysis.stale_reinitialization_count > 0 ? 'DEFECT_CANDIDATE'
          : (snapshotAnalysis.snapshot_count > 0 ? 'REINITIALIZATION_SIGNAL' : 'NOT_OBSERVED'),
        initial_snapshots_after_repeat: snapshotAnalysis.snapshot_count,
        stale_reinitializations: snapshotAnalysis.stale_reinitialization_count,
      },
      'TRD-RED-004': {
        state: noProvenance.length ? 'SYSTEM_CONTRACT_SIGNAL' : 'NOT_OBSERVED',
        contradictory_updates_without_provenance: noProvenance.length,
      },
    },
    invariant: 'A later accepted quote revision must not silently make visible market time materially older unless the payload explicitly identifies a different time domain or feed provenance.',
    causal_conclusion: reducerCandidate
      ? 'A conventional monotonic n/rev shallow-merge reducer is sufficient to reproduce visible time rollback from the observed public demo stream. A provenance-aware freshness guard prevents that deterministic client-state consequence.'
      : 'The bounded replay did not reach the configured threshold for a deterministic reducer-level defect candidate.',
    claim_boundary: contract.claim_boundary,
  };
}

function markdown(result) {
  const f = result.adjudication.findings;
  return `# Tradernet quote reducer integrity v0.2\n\n- Overall: **${result.adjudication.overall_verdict}**\n- Naive visible-time rollbacks: **${f['TRD-RED-001'].naive_visible_time_rollback_count}**\n- Guarded suppressions: **${f['TRD-RED-001'].guarded_suppressed_rollback_count}**\n- Backward-time updates with changed price/size: **${f['TRD-RED-002'].backward_time_updates_with_changed_ltp_or_lts}**\n- Repeated-subscription snapshots: **${f['TRD-RED-003'].initial_snapshots_after_repeat}**\n- Stale snapshot reinitializations: **${f['TRD-RED-003'].stale_reinitializations}**\n- Contradictory updates without provenance: **${f['TRD-RED-004'].contradictory_updates_without_provenance}**\n\n## Causal conclusion\n\n${result.adjudication.causal_conclusion}\n\n## Boundary\n\n${result.adjudication.claim_boundary}\n`;
}

function selfTest() {
  const contract = {
    rules: {
      material_market_time_regression_seconds: 60,
      minimum_rollbacks_for_candidate: 4,
      minimum_affected_tickers: 2,
      minimum_affected_connection_phases: 2,
      time_sensitive_fields: ['ltt', 'ltp', 'lts'],
      provenance_fields: ['feed', 'source'],
    },
    claim_boundary: 'test boundary',
  };
  const msg = (c, n, rev, ltt, ltp, init = 0, offset_ms = 1) => ({
    is_binary: false, offset_ms, sha256: `${c}-${n}`,
    text: JSON.stringify(['q', { c, n, rev, ltt, ltp, init }]),
  });
  const reconnect = { websocket: [
    { phase: 'before', messages: [msg('AAPL.US', 1, 1, '2026-01-01T10:15:00Z', 101), msg('AAPL.US', 2, 2, '2026-01-01T10:00:00Z', 100), msg('MSFT.US', 1, 1, '2026-01-01T10:15:00Z', 201), msg('MSFT.US', 2, 2, '2026-01-01T10:00:00Z', 200)] },
    { phase: 'after', messages: [msg('AAPL.US', 3, 3, '2026-01-01T10:16:00Z', 102), msg('AAPL.US', 4, 4, '2026-01-01T10:01:00Z', 99), msg('MSFT.US', 3, 3, '2026-01-01T10:16:00Z', 202), msg('MSFT.US', 4, 4, '2026-01-01T10:01:00Z', 199)] },
  ] };
  const idempotency = { lifecycle: { repeat_subscription_sent_at_ms: 4000 }, messages: [
    msg('AAPL.US', 5, 5, '2026-01-01T10:20:00Z', 103, 0, 1000),
    msg('AAPL.US', 4, 4, '2026-01-01T10:00:00Z', 99, 1, 5000),
  ] };
  const replay = replayQuotes(reconnectQuotes(reconnect), contract);
  const snapshots = analyzeRepeatedSnapshots(idempotency, contract);
  const result = adjudicate(replay, snapshots, contract);
  if (result.overall_verdict !== 'DEFECT_CANDIDATE') throw new Error('expected reducer defect candidate');
  if (result.findings['TRD-RED-002'].backward_time_updates_with_changed_ltp_or_lts !== 4) throw new Error('expected four price rollbacks');
  if (result.findings['TRD-RED-003'].stale_reinitializations !== 1) throw new Error('expected stale snapshot');
  console.log('self-test: ok');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) return selfTest();
  const [reconnect, idempotency, contract] = await Promise.all([
    fs.readFile(args.reconnectInput, 'utf8').then(JSON.parse),
    fs.readFile(args.idempotencyInput, 'utf8').then(JSON.parse),
    fs.readFile(args.contract, 'utf8').then(JSON.parse),
  ]);
  const reconnectReplay = replayQuotes(reconnectQuotes(reconnect), contract);
  const snapshotAnalysis = analyzeRepeatedSnapshots(idempotency, contract);
  const output = {
    schema_version: 'liminalqa-tradernet-quote-reducer-integrity-result-v1',
    generated_at: new Date().toISOString(),
    source_files: { reconnect: args.reconnectInput, idempotency: args.idempotencyInput, contract: args.contract },
    reconnect_replay: reconnectReplay,
    repeated_subscription_analysis: snapshotAnalysis,
    adjudication: adjudicate(reconnectReplay, snapshotAnalysis, contract),
  };
  const outputDir = path.resolve(args.outputDir);
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, 'tradernet-quote-reducer-integrity.json'), `${JSON.stringify(output, null, 2)}\n`, 'utf8');
  await fs.writeFile(path.join(outputDir, 'tradernet-quote-reducer-integrity.md'), markdown(output), 'utf8');
  console.log(JSON.stringify(output.adjudication, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 2;
});
