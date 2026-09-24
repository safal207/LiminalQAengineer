#!/usr/bin/env node
import fs from 'node:fs/promises';
import process from 'node:process';

function parseArgs(argv) {
  const args = { input: null, output: null, selfTest: false };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    const next = () => {
      if (index + 1 >= argv.length) throw new Error(`missing value for ${token}`);
      index += 1;
      return argv[index];
    };
    if (token === '--input') args.input = next();
    else if (token === '--output') args.output = next();
    else if (token === '--self-test') args.selfTest = true;
    else throw new Error(`unknown argument: ${token}`);
  }
  if (args.selfTest) return args;
  if (!args.input || !args.output) throw new Error('--input and --output are required');
  return args;
}

function parseTimestamp(value) {
  if (typeof value !== 'string' || value.length < 10) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseQuoteMessage(message) {
  if (message?.is_binary || typeof message?.text !== 'string') return null;
  let parsed;
  try {
    parsed = JSON.parse(message.text);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed) || parsed[0] !== 'q' || !parsed[1] || typeof parsed[1] !== 'object') return null;
  const payload = parsed[1];
  return {
    ticker: typeof payload.c === 'string' ? payload.c : null,
    sequence: Number.isFinite(payload.n) ? payload.n : null,
    revision: Number.isFinite(payload.rev) ? payload.rev : null,
    initial_snapshot: payload.init === 1 || payload.init === true,
    market_timestamp: typeof payload.ltt === 'string' ? payload.ltt : null,
    market_timestamp_ms: parseTimestamp(payload.ltt),
    server_timestamp: typeof payload.acc_srv_tm === 'string' ? payload.acc_srv_tm : null,
    ltp: Number.isFinite(payload.ltp) ? payload.ltp : null,
    lts: Number.isFinite(payload.lts) ? payload.lts : null,
    changed_fields: Object.keys(payload).sort(),
    offset_ms: message.offset_ms,
    sha256: message.sha256,
  };
}

function analyzePhase(phase) {
  const byTicker = new Map();
  for (const message of phase.messages ?? []) {
    const quote = parseQuoteMessage(message);
    if (!quote?.ticker) continue;
    if (!byTicker.has(quote.ticker)) byTicker.set(quote.ticker, []);
    byTicker.get(quote.ticker).push(quote);
  }

  const tickers = {};
  const contradictions = [];
  for (const [ticker, quotes] of byTicker) {
    const local = [];
    let backwardJumps = 0;
    let forwardNear15mJumps = 0;
    let backwardNear15mJumps = 0;
    for (let index = 1; index < quotes.length; index += 1) {
      const previous = quotes[index - 1];
      const current = quotes[index];
      if (previous.market_timestamp_ms === null || current.market_timestamp_ms === null) continue;
      const deltaSeconds = (current.market_timestamp_ms - previous.market_timestamp_ms) / 1000;
      const sequenceAdvanced = previous.sequence === null || current.sequence === null || current.sequence > previous.sequence;
      const revisionAdvanced = previous.revision === null || current.revision === null || current.revision > previous.revision;
      if (deltaSeconds < -60 && sequenceAdvanced && revisionAdvanced) {
        const item = {
          phase: phase.phase,
          ticker,
          delta_seconds: deltaSeconds,
          near_15_minutes: Math.abs(Math.abs(deltaSeconds) - 900) <= 60,
          previous: {
            sequence: previous.sequence,
            revision: previous.revision,
            market_timestamp: previous.market_timestamp,
            ltp: previous.ltp,
            lts: previous.lts,
            changed_fields: previous.changed_fields,
            sha256: previous.sha256,
          },
          current: {
            sequence: current.sequence,
            revision: current.revision,
            market_timestamp: current.market_timestamp,
            ltp: current.ltp,
            lts: current.lts,
            changed_fields: current.changed_fields,
            sha256: current.sha256,
          },
        };
        local.push(item);
        contradictions.push(item);
        backwardJumps += 1;
        if (item.near_15_minutes) backwardNear15mJumps += 1;
      }
      if (deltaSeconds > 60 && Math.abs(deltaSeconds - 900) <= 60) forwardNear15mJumps += 1;
    }
    tickers[ticker] = {
      quote_count: quotes.length,
      timestamps_present: quotes.filter((quote) => quote.market_timestamp_ms !== null).length,
      backward_market_time_jumps: backwardJumps,
      backward_near_15_minute_jumps: backwardNear15mJumps,
      forward_near_15_minute_jumps: forwardNear15mJumps,
      contradictions: local.slice(0, 12),
    };
  }

  return {
    phase: phase.phase,
    ticker_count: Object.keys(tickers).length,
    contradiction_count: contradictions.length,
    tickers,
    contradictions: contradictions.slice(0, 20),
  };
}

function adjudicate(phases) {
  const contradictions = phases.flatMap((phase) => phase.contradictions);
  const affectedTickers = [...new Set(contradictions.map((item) => item.ticker))].sort();
  const near15 = contradictions.filter((item) => item.near_15_minutes);
  const repeatedAcrossPhases = phases.filter((phase) => phase.contradiction_count > 0).length >= 2;
  const defectCandidate = contradictions.length >= 4 && affectedTickers.length >= 2 && near15.length >= 4 && repeatedAcrossPhases;
  return {
    verdict: defectCandidate ? 'DEFECT_CANDIDATE' : contradictions.length ? 'SIGNAL' : 'NOT_OBSERVED',
    temporal_contradiction_count: contradictions.length,
    affected_tickers: affectedTickers,
    near_15_minute_backward_jump_count: near15.length,
    repeated_across_both_connection_phases: repeatedAcrossPhases,
    invariant: 'For one ticker stream, a later sequence/revision must not silently replace last-trade time with a materially older value unless feed provenance or timestamp semantics explicitly distinguish the update.',
    causal_hypotheses: [
      'A real-time and approximately 15-minute-delayed source are multiplexed into the same q event without a source marker.',
      'The ltt field has different undocumented semantics for different partial-update producers.',
      'A reducer that blindly merges partial q payloads can roll visible last price/time backward despite monotonic n and rev.',
    ],
    impact: 'Clients may display a fresh connection and increasing revisions while intermittently showing stale trade time or stale last price. This is a market-data integrity risk, not proof of trade execution impact.',
    claim_boundary: 'The evidence proves non-monotonic ltt values in the public demo quote stream. It does not prove which upstream venue or entitlement path produced each update, because the payload exposes no explicit feed provenance.',
  };
}

function selfTest() {
  const phase = {
    phase: 'test',
    messages: [
      { is_binary: false, offset_ms: 1, sha256: 'a', text: '["q",{"c":"AAPL.US","n":1,"rev":10,"ltt":"2026-01-01T10:15:00","ltp":101}]' },
      { is_binary: false, offset_ms: 2, sha256: 'b', text: '["q",{"c":"AAPL.US","n":2,"rev":11,"ltt":"2026-01-01T10:00:01","ltp":100}]' },
    ],
  };
  const result = analyzePhase(phase);
  if (result.contradiction_count !== 1) throw new Error('expected one contradiction');
  if (!result.contradictions[0].near_15_minutes) throw new Error('expected near-15-minute classification');
  console.log('self-test: ok');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) return selfTest();
  const input = JSON.parse(await fs.readFile(args.input, 'utf8'));
  if (!Array.isArray(input.websocket) || input.websocket.length !== 2) throw new Error('expected exactly two websocket phases');
  const phases = input.websocket.map(analyzePhase);
  const output = {
    schema_version: 'liminalqa-tradernet-public-quote-temporal-integrity-v1',
    source_result: args.input,
    generated_at: new Date().toISOString(),
    phases,
    adjudication: adjudicate(phases),
  };
  await fs.writeFile(args.output, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(output.adjudication, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 2;
});
