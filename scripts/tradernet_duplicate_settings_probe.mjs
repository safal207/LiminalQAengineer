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
    if (!value || value.startsWith('--')) args[key] = true;
    else {
      args[key] = value;
      i += 1;
    }
  }
  for (const key of ['chrome', 'output-dir']) {
    if (!args[key]) throw new Error(`missing --${key}`);
  }
  return args;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash('sha256').update(value).digest('hex');
const TARGET = 'https://tradernet.ru/charts/MICEXINDEXCF?site_lang=ru';
const GET_SETTINGS = 'https://tradernet.ru/stocks/security-info/ajax-get-user-settings/';
const SET_SETTINGS = 'https://tradernet.ru/stocks/security-info/ajax-set-user-settings/';

function safeStack(initiator) {
  const frames = initiator?.stack?.callFrames || [];
  return frames.slice(0, 5).map((frame) => {
    let url = '<inline>';
    try {
      const parsed = new URL(frame.url);
      url = `${parsed.origin}${parsed.pathname}`;
    } catch {}
    return {
      function_name: frame.functionName || '<anonymous>',
      url,
      line: frame.lineNumber,
      column: frame.columnNumber
    };
  });
}

function bodyDigest(payload) {
  if (!payload) return { sha256: sha256(Buffer.alloc(0)), bytes: 0 };
  const buffer = payload.base64Encoded
    ? Buffer.from(payload.body, 'base64')
    : Buffer.from(payload.body, 'utf8');
  return { sha256: sha256(buffer), bytes: buffer.length };
}

function intervalsOverlap(a, b) {
  const aEnd = a.finished_at_ms ?? Number.POSITIVE_INFINITY;
  const bEnd = b.finished_at_ms ?? Number.POSITIVE_INFINITY;
  return a.started_at_ms < bEnd && b.started_at_ms < aEnd;
}

async function runRound(browser, chromeProfile, round) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(chromeProfile.user_agent);
  await page.setViewport(chromeProfile.viewport);
  const client = await page.target().createCDPSession();
  await client.send('Network.enable');
  await client.send('Network.setCacheDisabled', { cacheDisabled: true });
  await client.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: chromeProfile.network.latency_ms,
    downloadThroughput: chromeProfile.network.download_bytes_per_second,
    uploadThroughput: chromeProfile.network.upload_bytes_per_second,
    connectionType: chromeProfile.network.connection_type
  });

  const startedAt = Date.now();
  const now = () => Date.now() - startedAt;
  const tracked = new Map();
  const naturalSetRequests = [];
  const consoleErrors = [];

  client.on('Network.requestWillBeSent', ({ requestId, request, type, initiator }) => {
    if (request.url !== GET_SETTINGS && request.url !== SET_SETTINGS) return;
    const record = {
      id_hash: sha256(Buffer.from(requestId)).slice(0, 16),
      endpoint: request.url,
      started_at_ms: now(),
      method: request.method,
      resource_type: type,
      initiator_type: initiator?.type || null,
      initiator_stack: safeStack(initiator),
      has_post_data: Boolean(request.hasPostData),
      post_data_bytes: request.postData ? Buffer.byteLength(request.postData, 'utf8') : 0,
      response_status: null,
      response_mime_type: null,
      response_protocol: null,
      response_body_sha256: null,
      response_body_bytes: null,
      encoded_data_length: null,
      finished_at_ms: null,
      failed: false,
      failure_text_hash: null
    };
    tracked.set(requestId, record);
    if (request.url === SET_SETTINGS) naturalSetRequests.push(record);
  });

  client.on('Network.responseReceived', ({ requestId, response }) => {
    const record = tracked.get(requestId);
    if (!record) return;
    record.response_status = response.status;
    record.response_mime_type = response.mimeType;
    record.response_protocol = response.protocol;
  });

  client.on('Network.loadingFinished', async ({ requestId, encodedDataLength }) => {
    const record = tracked.get(requestId);
    if (!record) return;
    record.finished_at_ms = now();
    record.encoded_data_length = encodedDataLength;
    try {
      const payload = await client.send('Network.getResponseBody', { requestId });
      const digest = bodyDigest(payload);
      record.response_body_sha256 = digest.sha256;
      record.response_body_bytes = digest.bytes;
    } catch {
      record.response_body_sha256 = null;
      record.response_body_bytes = null;
    }
  });

  client.on('Network.loadingFailed', ({ requestId, errorText }) => {
    const record = tracked.get(requestId);
    if (!record) return;
    record.finished_at_ms = now();
    record.failed = true;
    record.failure_text_hash = sha256(Buffer.from(errorText || ''));
  });

  page.on('console', (message) => {
    if (message.type() !== 'error' || consoleErrors.length >= 20) return;
    consoleErrors.push({ at_ms: now(), text_sha256: sha256(Buffer.from(message.text())) });
  });

  let navigationStatus = null;
  try {
    const response = await page.goto(TARGET, { waitUntil: 'domcontentloaded', timeout: 60000 });
    navigationStatus = response?.status() ?? null;
    await sleep(15000);
  } finally {
    await client.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
      connectionType: 'none'
    }).catch(() => {});
  }

  const getRequests = [...tracked.values()]
    .filter((item) => item.endpoint === GET_SETTINGS)
    .sort((a, b) => a.started_at_ms - b.started_at_ms);
  const overlapPairs = [];
  for (let i = 0; i < getRequests.length; i += 1) {
    for (let j = i + 1; j < getRequests.length; j += 1) {
      if (intervalsOverlap(getRequests[i], getRequests[j])) {
        overlapPairs.push([getRequests[i].id_hash, getRequests[j].id_hash]);
      }
    }
  }
  const responseHashes = [...new Set(getRequests.map((item) => item.response_body_sha256).filter(Boolean))];
  const roundResult = {
    round,
    target: TARGET,
    navigation_status: navigationStatus,
    get_settings_requests: getRequests,
    set_settings_requests: naturalSetRequests,
    get_settings_count: getRequests.length,
    overlap_pairs: overlapPairs,
    has_overlap: overlapPairs.length > 0,
    response_hash_count: responseHashes.length,
    all_success_200: getRequests.length > 0 && getRequests.every((item) => item.response_status === 200 && !item.failed),
    identical_response_body: getRequests.length >= 2 && responseHashes.length === 1,
    console_error_count: consoleErrors.length,
    duration_ms: now()
  };

  await page.close();
  await context.close();
  return roundResult;
}

function classify(rounds) {
  const duplicateRounds = rounds.filter((round) =>
    round.get_settings_count >= 2 &&
    round.has_overlap &&
    round.all_success_200 &&
    round.identical_response_body
  );
  const mixedTransportRounds = rounds.filter((round) => {
    const types = new Set(round.get_settings_requests.map((item) => item.resource_type));
    return types.has('Fetch') && types.has('XHR');
  });

  if (duplicateRounds.length >= 2) {
    return {
      verdict: 'CONFIRMED_REDUNDANT_DUPLICATE_REQUEST',
      confidence: 'HIGH',
      severity: 'P2_PERFORMANCE_RELIABILITY',
      evidence: `${duplicateRounds.length}/3 fresh contexts issued overlapping successful requests to the same settings endpoint and received byte-identical response bodies. ${mixedTransportRounds.length}/3 rounds used both Fetch and XHR.`
    };
  }
  if (duplicateRounds.length === 1 || rounds.some((round) => round.get_settings_count >= 2)) {
    return {
      verdict: 'NEEDS_EVIDENCE',
      confidence: 'MEDIUM',
      severity: 'UNASSIGNED',
      evidence: 'Duplicate settings retrieval appeared but did not satisfy the 2/3 reproducibility and identity threshold.'
    };
  }
  return {
    verdict: 'NOT_REPRODUCED',
    confidence: 'HIGH',
    severity: 'UNASSIGNED',
    evidence: 'No fresh context produced two settings retrievals during the bounded observation window.'
  };
}

async function main() {
  const args = parseArgs(process.argv);
  const outputDir = path.resolve(args['output-dir']);
  fs.mkdirSync(outputDir, { recursive: true });

  const profile = {
    user_agent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    viewport: { width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
    network: {
      latency_ms: 40,
      download_bytes_per_second: 1250000,
      upload_bytes_per_second: 625000,
      connection_type: 'ethernet'
    }
  };

  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage']
  });
  const rounds = [];
  try {
    for (let round = 1; round <= 3; round += 1) {
      rounds.push(await runRound(browser, profile, round));
    }
  } finally {
    await browser.close();
  }

  const result = {
    schema_version: 'liminalqa-tradernet-duplicate-settings-v1',
    target: TARGET,
    endpoint: GET_SETTINGS,
    rounds,
    decision: classify(rounds),
    boundaries: {
      public_page_only: true,
      natural_requests_only: true,
      fresh_contexts: 3,
      direct_api_calls: false,
      raw_response_bodies_stored: false,
      raw_request_bodies_stored: false,
      authentication: false,
      financial_operations: false,
      load_testing: false
    },
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
  const resultPath = path.join(outputDir, 'duplicate-settings-result.json');
  fs.writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`);

  const lines = [
    '# Tradernet duplicate settings request experiment',
    '',
    `Verdict: **${result.decision.verdict}**`,
    '',
    '| Round | Requests | Overlap | 200 | Identical response hash | Resource types |',
    '|---:|---:|---|---|---|---|',
    ...rounds.map((round) => `| ${round.round} | ${round.get_settings_count} | ${round.has_overlap} | ${round.all_success_200} | ${round.identical_response_body} | ${[...new Set(round.get_settings_requests.map((item) => item.resource_type))].join(', ')} |`),
    '',
    result.decision.evidence,
    '',
    'Raw settings response bodies and request bodies were never persisted.'
  ];
  fs.writeFileSync(path.join(outputDir, 'summary.md'), `${lines.join('\n')}\n`);
  fs.writeFileSync(path.join(outputDir, 'manifest.sha256'), [
    `${sha256(fs.readFileSync(resultPath))}  duplicate-settings-result.json`,
    `${sha256(fs.readFileSync(path.join(outputDir, 'summary.md')))}  summary.md`
  ].join('\n') + '\n');
  console.log(lines.join('\n'));
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});
