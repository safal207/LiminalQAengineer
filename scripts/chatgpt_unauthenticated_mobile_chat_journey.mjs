import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) out[key] = true;
    else {
      out[key] = value;
      i += 1;
    }
  }
  return out;
}

function sha256(value) {
  return crypto.createHash('sha256').update(String(value ?? '')).digest('hex');
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function writeJson(file, value) {
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function safeUrl(raw) {
  try {
    const url = new URL(raw);
    return `${url.origin}${url.pathname}`;
  } catch {
    return sha256(raw);
  }
}

const args = parseArgs(process.argv);
const configPath = args.config;
const chromePath = args.chrome;
const outputDir = args['output-dir'];

if (!configPath || !chromePath || !outputDir) {
  throw new Error('Required: --config <path> --chrome <path> --output-dir <path>');
}

const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
ensureDir(outputDir);
ensureDir(path.join(outputDir, 'screenshots'));

if (config.boundaries.public_unauthenticated_only !== true) throw new Error('public boundary required');
if (config.boundaries.maximum_prompt_submissions !== 1) throw new Error('exactly one prompt required');
if (config.boundaries.login_submission !== false) throw new Error('login submission must remain disabled');
if (config.boundaries.direct_application_api_testing !== false) throw new Error('direct API testing must remain disabled');

const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: 'new',
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-background-networking',
    '--disable-default-apps',
    '--disable-extensions',
    '--disable-sync',
    '--metrics-recording-only',
    '--mute-audio',
    '--no-first-run',
  ],
});

const page = await browser.newPage();
await page.setUserAgent(config.user_agent);
await page.setViewport(config.viewport);

const consoleMessages = [];
const pageErrors = [];
const failedRequests = [];
const errorResponses = [];

page.on('console', (message) => {
  if (['error', 'warn'].includes(message.type())) {
    consoleMessages.push({
      type: message.type(),
      text_sha256: sha256(message.text()),
      text_length: message.text().length,
      location: message.location() ? {
        url: safeUrl(message.location().url || ''),
        lineNumber: message.location().lineNumber ?? null,
        columnNumber: message.location().columnNumber ?? null,
      } : null,
    });
  }
});

page.on('pageerror', (error) => {
  pageErrors.push({
    name: error?.name || 'Error',
    message_sha256: sha256(error?.message || ''),
    message_length: (error?.message || '').length,
  });
});

page.on('requestfailed', (request) => {
  const url = request.url();
  if (!url.startsWith('https://chatgpt.com/')) return;
  failedRequests.push({
    url: safeUrl(url),
    method: request.method(),
    failure: request.failure()?.errorText || null,
  });
});

page.on('response', (response) => {
  const url = response.url();
  if (!url.startsWith('https://chatgpt.com/')) return;
  if (response.status() >= 400) {
    errorResponses.push({
      url: safeUrl(url),
      status: response.status(),
      method: response.request().method(),
    });
  }
});

async function inspect() {
  const raw = await page.evaluate(() => {
    const visible = (el) => {
      const style = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity || 1) > 0 && r.width > 0 && r.height > 0;
    };
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        x: Math.round(r.x * 100) / 100,
        y: Math.round(r.y * 100) / 100,
        width: Math.round(r.width * 100) / 100,
        height: Math.round(r.height * 100) / 100,
        right: Math.round(r.right * 100) / 100,
        bottom: Math.round(r.bottom * 100) / 100,
      };
    };
    const nameOf = (el) => (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.getAttribute('data-testid') ||
      el.innerText ||
      el.textContent ||
      ''
    ).trim().replace(/\s+/g, ' ').slice(0, 180);

    const all = [...document.querySelectorAll('button, a, textarea, input, [role="button"], [contenteditable="true"]')]
      .filter(visible);
    const controls = all.map((el) => ({
      name: nameOf(el),
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type'),
      testid: el.getAttribute('data-testid'),
      rect: rect(el),
    }));

    const composer = [...document.querySelectorAll('textarea, [contenteditable="true"]')].find(visible) || null;
    const form = composer?.closest('form') || null;
    const roleMessages = [...document.querySelectorAll('[data-message-author-role]')]
      .filter(visible)
      .map((el) => ({ role: el.getAttribute('data-message-author-role'), text: (el.innerText || el.textContent || '').trim() }));
    const articleTexts = [...document.querySelectorAll('article')]
      .filter(visible)
      .map((el) => (el.innerText || el.textContent || '').trim())
      .filter(Boolean);
    const candidateMessages = roleMessages.length
      ? roleMessages
      : articleTexts.map((text, index) => ({ role: index % 2 === 0 ? 'unknown' : 'assistant-candidate', text }));

    const stopVisible = all.some((el) => /stop/i.test(nameOf(el)));
    const sendVisible = all.some((el) => /send message|send$/i.test(nameOf(el)) || el.getAttribute('data-testid') === 'send-button');
    const loginVisible = all.some((el) => /^log in$/i.test(nameOf(el)) || /log in or sign up/i.test(nameOf(el)));
    const accountLikeVisible = all.some((el) => /account|workspace|profile/i.test(nameOf(el)));

    return {
      title: document.title,
      final_url: location.href,
      viewport: {
        inner_width: innerWidth,
        inner_height: innerHeight,
        visual_width: visualViewport?.width ?? null,
        visual_height: visualViewport?.height ?? null,
        visual_offset_top: visualViewport?.offsetTop ?? null,
        document_width: document.documentElement.scrollWidth,
        document_height: document.documentElement.scrollHeight,
        horizontal_overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      },
      scroll: {
        y: scrollY,
        max_y: Math.max(0, document.documentElement.scrollHeight - innerHeight),
        distance_to_bottom: Math.max(0, document.documentElement.scrollHeight - innerHeight - scrollY),
      },
      headings: [...document.querySelectorAll('h1,h2,h3')].filter(visible).map((el) => ({
        level: el.tagName.toLowerCase(),
        text: nameOf(el),
        rect: rect(el),
      })),
      controls,
      composer: composer ? {
        name: nameOf(composer),
        rect: rect(composer),
        form_rect: rect(form),
        value: 'value' in composer ? composer.value : composer.innerText,
      } : null,
      messages: candidateMessages,
      stop_visible: stopVisible,
      send_visible: sendVisible,
      login_visible: loginVisible,
      account_like_visible: accountLikeVisible,
    };
  });

  const messages = raw.messages.map((message) => ({
    role: message.role,
    text_length: message.text.length,
    text_sha256: sha256(message.text),
  }));
  const responseTexts = raw.messages
    .filter((message) => message.role === 'assistant' || message.role === 'assistant-candidate')
    .map((message) => message.text);

  return {
    persisted: {
      ...raw,
      final_url: safeUrl(raw.final_url),
      controls: raw.controls.map((control) => ({
        ...control,
        name: /^(Open sidebar|Close sidebar|Log in|Add files and more|Start dictation|Send message|Stop generating|Stop|Try again|Regenerate|New chat|Search chats)$/i.test(control.name)
          ? control.name
          : `sha256:${sha256(control.name)}`,
      })),
      composer: raw.composer ? {
        name: raw.composer.name,
        rect: raw.composer.rect,
        form_rect: raw.composer.form_rect,
        draft_length: raw.composer.value.length,
        draft_sha256: sha256(raw.composer.value),
      } : null,
      messages,
    },
    transient: {
      response_texts: responseTexts,
      composer_value: raw.composer?.value || '',
    },
  };
}

async function screenshot(label) {
  const file = path.join(outputDir, 'screenshots', `${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return path.relative(outputDir, file);
}

async function snapshot(label, withScreenshot = true) {
  const state = await inspect();
  return {
    label,
    captured_at: new Date().toISOString(),
    ...state.persisted,
    screenshot: withScreenshot ? await screenshot(label) : null,
    _transient: state.transient,
  };
}

let result;
try {
  const navigation = await page.goto(config.target_url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await sleep(config.initial_wait_ms);
  const initial = await snapshot('01-initial-signed-out-mobile');

  if (navigation?.status() !== 200 || !initial.login_visible || initial.account_like_visible) {
    result = {
      schema_version: config.schema_version,
      case_id: config.case_id,
      verdict: 'SIGNED_OUT_STATE_NOT_PROVEN',
      navigation_status: navigation?.status() ?? null,
      initial: { ...initial, _transient: undefined },
    };
  } else if (!initial.composer) {
    result = {
      schema_version: config.schema_version,
      case_id: config.case_id,
      verdict: 'PUBLIC_COMPOSER_NOT_AVAILABLE',
      initial: { ...initial, _transient: undefined },
    };
  } else {
    const composerHandle = await page.$('textarea') || await page.$('[contenteditable="true"]');
    if (!composerHandle) throw new Error('Composer disappeared before prompt entry');
    await composerHandle.focus();
    await page.keyboard.type(config.prompt, { delay: 20 });
    const drafted = await snapshot('02-benign-prompt-drafted');

    const sendHandle = await page.$('button[data-testid="send-button"]')
      || await page.$('button[aria-label="Send message"]')
      || await page.$('button[type="submit"]');
    if (!sendHandle) throw new Error('Send control not found');
    await sendHandle.click();

    const streamStartedAt = Date.now();
    let streamingSnapshot = null;
    let lastAssistantLength = -1;
    let lastAssistantChangeAt = Date.now();
    let completionState = null;
    const samples = [];

    while (Date.now() - streamStartedAt < config.stream_timeout_ms) {
      await sleep(500);
      const sample = await snapshot(`sample-${samples.length + 1}`, false);
      const transientResponse = sample._transient.response_texts.join('\n');
      const assistantLength = transientResponse.length;
      if (assistantLength !== lastAssistantLength) {
        lastAssistantLength = assistantLength;
        lastAssistantChangeAt = Date.now();
      }
      samples.push({
        at_ms: Date.now() - streamStartedAt,
        assistant_text_length: assistantLength,
        assistant_text_sha256: sha256(transientResponse),
        stop_visible: sample.stop_visible,
        send_visible: sample.send_visible,
        horizontal_overflow: sample.viewport.horizontal_overflow,
        distance_to_bottom: sample.scroll.distance_to_bottom,
      });
      if (sample.stop_visible && !streamingSnapshot) {
        streamingSnapshot = await snapshot('03-streaming-active');
      }
      const stableFor = Date.now() - lastAssistantChangeAt;
      if (assistantLength > 0 && !sample.stop_visible && stableFor >= config.stability_window_ms) {
        completionState = sample;
        break;
      }
    }

    const completed = await snapshot('04-response-complete');
    const responseText = completed._transient.response_texts.join('\n');
    await page.setViewport(config.compact_viewport);
    await sleep(1200);
    const compact = await snapshot('05-compact-height-after-response');

    result = {
      schema_version: config.schema_version,
      case_id: config.case_id,
      generated_at: new Date().toISOString(),
      exact_scope: 'one benign prompt on public signed-out mobile web',
      prompt_submission_count: 1,
      prompt_sha256: sha256(config.prompt),
      prompt_length: config.prompt.length,
      expected_response_fragment_present: responseText.includes(config.expected_response_fragment),
      response_text_length: responseText.length,
      response_text_sha256: sha256(responseText),
      stream_observed: Boolean(streamingSnapshot),
      completion_observed: Boolean(completionState) || responseText.length > 0,
      samples,
      checkpoints: {
        initial: { ...initial, _transient: undefined },
        drafted: { ...drafted, _transient: undefined },
        streaming: streamingSnapshot ? { ...streamingSnapshot, _transient: undefined } : null,
        completed: { ...completed, _transient: undefined },
        compact: { ...compact, _transient: undefined },
      },
      runtime: {
        console_messages: consoleMessages,
        page_errors: pageErrors,
        failed_first_party_requests: failedRequests,
        first_party_error_responses: errorResponses,
      },
      verdict: responseText.includes(config.expected_response_fragment)
        ? 'UNAUTHENTICATED_MOBILE_CHAT_PASS'
        : (responseText.length > 0 ? 'RESPONSE_COMPLETED_EXPECTATION_MISMATCH' : 'NO_ASSISTANT_RESPONSE_OBSERVED'),
      authority: config.boundaries,
    };
  }
} catch (error) {
  result = {
    schema_version: config.schema_version,
    case_id: config.case_id,
    generated_at: new Date().toISOString(),
    verdict: 'INSTRUMENTATION_OR_PRODUCT_FLOW_ERROR',
    error: {
      name: error?.name || 'Error',
      message: error?.message || String(error),
      stack_sha256: sha256(error?.stack || ''),
    },
    runtime: {
      console_messages: consoleMessages,
      page_errors: pageErrors,
      failed_first_party_requests: failedRequests,
      first_party_error_responses: errorResponses,
    },
    authority: config.boundaries,
  };
}

await browser.close();
writeJson(path.join(outputDir, 'chatgpt-unauth-mobile-chat-result.json'), result);

const summary = [
  '# ChatGPT unauthenticated mobile-chat journey',
  '',
  `Case: \`${config.case_id}\``,
  `Verdict: \`${result.verdict}\``,
  '',
  '## Boundary',
  '',
  'One benign public prompt only. No login, account, private chat, file upload, permission request, direct API testing, challenge bypass, fuzzing or load testing.',
  '',
  '## Result',
  '',
  `- Prompt submissions: ${result.prompt_submission_count ?? 0}`,
  `- Streaming observed: ${result.stream_observed ?? false}`,
  `- Completion observed: ${result.completion_observed ?? false}`,
  `- Expected response fragment present: ${result.expected_response_fragment_present ?? false}`,
  `- Response length: ${result.response_text_length ?? 0}`,
  `- Console warnings/errors captured: ${result.runtime?.console_messages?.length ?? 0}`,
  `- Page errors: ${result.runtime?.page_errors?.length ?? 0}`,
  `- First-party HTTP error responses: ${result.runtime?.first_party_error_responses?.length ?? 0}`,
  '',
  'Detector signals require screenshot/task adjudication before any product-defect claim.',
  '',
].join('\n');
fs.writeFileSync(path.join(outputDir, 'chatgpt-unauth-mobile-chat-summary.md'), summary, 'utf8');
console.log(summary);
