import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';
import puppeteer from 'puppeteer-core';

function argsOf(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue;
    out[argv[i].slice(2)] = argv[i + 1];
    i += 1;
  }
  return out;
}

const sha256 = (value) => crypto.createHash('sha256').update(String(value ?? '')).digest('hex');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const cli = argsOf(process.argv);
if (!cli.config || !cli.chrome || !cli['output-dir']) throw new Error('Missing required arguments');

const config = JSON.parse(fs.readFileSync(cli.config, 'utf8'));
const outputDir = cli['output-dir'];
fs.mkdirSync(path.join(outputDir, 'screenshots'), { recursive: true });

if (config.boundaries.public_unauthenticated_only !== true) throw new Error('public unauthenticated boundary required');
if (config.boundaries.maximum_prompt_submissions !== 1) throw new Error('one prompt only');
if (config.boundaries.login_submission !== false) throw new Error('login submission forbidden');
if (config.boundaries.direct_application_api_testing !== false) throw new Error('direct API testing forbidden');

const browser = await puppeteer.launch({
  executablePath: cli.chrome,
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--mute-audio', '--no-first-run'],
});
const page = await browser.newPage();
await page.setUserAgent(config.user_agent);
await page.setViewport(config.viewport);

const consoleSignals = [];
const pageErrors = [];
const failedRequests = [];
const errorResponses = [];

page.on('console', (message) => {
  if (!['warn', 'error'].includes(message.type())) return;
  consoleSignals.push({ type: message.type(), text_length: message.text().length, text_sha256: sha256(message.text()) });
});
page.on('pageerror', (error) => pageErrors.push({ name: error?.name || 'Error', message_sha256: sha256(error?.message || '') }));
page.on('requestfailed', (request) => {
  if (!request.url().startsWith('https://chatgpt.com/')) return;
  failedRequests.push({ url_path_sha256: sha256(new URL(request.url()).pathname), method: request.method(), failure: request.failure()?.errorText || null });
});
page.on('response', (response) => {
  if (!response.url().startsWith('https://chatgpt.com/') || response.status() < 400) return;
  errorResponses.push({ url_path_sha256: sha256(new URL(response.url()).pathname), status: response.status(), method: response.request().method() });
});

async function state(expected) {
  return page.evaluate((expectedText) => {
    const visible = (el) => {
      const style = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && r.width > 0 && r.height > 0;
    };
    const name = (el) => (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.innerText || el.textContent || '')
      .trim().replace(/\s+/g, ' ');
    const box = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom };
    };
    const controls = [...document.querySelectorAll('button,a,textarea,input,[role="button"],[contenteditable="true"]')].filter(visible);
    const composer = [...document.querySelectorAll('textarea,[contenteditable="true"]')].find(visible) || null;
    const exactCandidates = [...document.querySelectorAll('body *')]
      .filter(visible)
      .filter((el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ') === expectedText)
      .map((el) => ({ tag: el.tagName.toLowerCase(), rect: box(el) }))
      .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
    return {
      url: location.origin + location.pathname,
      title: document.title,
      viewport: {
        inner_width: innerWidth,
        inner_height: innerHeight,
        visual_width: visualViewport?.width ?? null,
        visual_height: visualViewport?.height ?? null,
        document_width: document.documentElement.scrollWidth,
        document_height: document.documentElement.scrollHeight,
        horizontal_overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      },
      scroll: {
        y: scrollY,
        distance_to_bottom: Math.max(0, document.documentElement.scrollHeight - innerHeight - scrollY),
      },
      login_visible: controls.some((el) => /^log in$/i.test(name(el))),
      account_like_visible: controls.some((el) => /account|workspace|profile/i.test(name(el))),
      send_visible: controls.some((el) => /send message|send$/i.test(name(el)) || el.getAttribute('data-testid') === 'send-button'),
      stop_visible: controls.some((el) => /stop/i.test(name(el))),
      composer: composer ? {
        rect: box(composer),
        container_rect: box(composer.closest('form')),
        draft_length: ('value' in composer ? composer.value : composer.innerText || '').length,
      } : null,
      expected_exact_visible: exactCandidates.length > 0,
      expected_exact_element_count: exactCandidates.length,
      expected_exact_smallest_rect: exactCandidates[0]?.rect || null,
      control_geometry: controls.map((el) => ({
        name: /^(Open sidebar|Close sidebar|Log in|Add files and more|Start dictation|Send message|Stop generating|Stop|Try again|Regenerate)$/i.test(name(el)) ? name(el) : `sha256:${name(el).length}`,
        rect: box(el),
      })),
    };
  }, expected);
}

async function shot(name) {
  const file = path.join(outputDir, 'screenshots', `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return path.relative(outputDir, file);
}

const result = {
  schema_version: 'liminalqa-chatgpt-unauth-mobile-chat-v2',
  case_id: config.case_id,
  generated_at: new Date().toISOString(),
  prompt_submission_count: 0,
  prompt_sha256: sha256(config.prompt),
  prompt_length: config.prompt.length,
  checkpoints: {},
  samples: [],
  runtime: {},
  authority: config.boundaries,
};

try {
  const navigation = await page.goto(config.target_url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await sleep(config.initial_wait_ms);
  result.checkpoints.initial = { ...(await state(config.expected_response_fragment)), screenshot: await shot('01-initial-signed-out-mobile') };

  if (navigation?.status() !== 200 || !result.checkpoints.initial.login_visible || result.checkpoints.initial.account_like_visible) {
    result.verdict = 'SIGNED_OUT_STATE_NOT_PROVEN';
  } else if (!result.checkpoints.initial.composer) {
    result.verdict = 'PUBLIC_COMPOSER_NOT_AVAILABLE';
  } else {
    const composer = await page.$('textarea') || await page.$('[contenteditable="true"]');
    await composer.focus();
    await page.keyboard.type(config.prompt, { delay: 20 });
    result.checkpoints.drafted = { ...(await state(config.expected_response_fragment)), screenshot: await shot('02-benign-prompt-drafted') };

    const send = await page.$('button[data-testid="send-button"]') || await page.$('button[aria-label="Send message"]') || await page.$('button[type="submit"]');
    if (!send) throw new Error('Send control not found');
    await send.click();
    result.prompt_submission_count = 1;

    const started = Date.now();
    let streamingCaptured = false;
    let completed = false;
    while (Date.now() - started < config.stream_timeout_ms) {
      await sleep(400);
      const current = await state(config.expected_response_fragment);
      result.samples.push({
        at_ms: Date.now() - started,
        stop_visible: current.stop_visible,
        send_visible: current.send_visible,
        expected_exact_visible: current.expected_exact_visible,
        horizontal_overflow: current.viewport.horizontal_overflow,
        distance_to_bottom: current.scroll.distance_to_bottom,
      });
      if (current.stop_visible && !streamingCaptured) {
        result.checkpoints.streaming = { ...current, screenshot: await shot('03-streaming-active') };
        streamingCaptured = true;
      }
      if (current.expected_exact_visible && !current.stop_visible) {
        completed = true;
        break;
      }
    }

    result.checkpoints.completed = { ...(await state(config.expected_response_fragment)), screenshot: await shot('04-response-complete') };
    await page.setViewport(config.compact_viewport);
    await sleep(1200);
    result.checkpoints.compact = { ...(await state(config.expected_response_fragment)), screenshot: await shot('05-compact-height-after-response') };

    result.stream_observed = streamingCaptured;
    result.completion_observed = completed || result.checkpoints.completed.expected_exact_visible;
    result.expected_response_fragment_present = result.checkpoints.completed.expected_exact_visible;
    result.response_text_length = result.expected_response_fragment_present ? config.expected_response_fragment.length : 0;
    result.response_text_sha256 = result.expected_response_fragment_present ? sha256(config.expected_response_fragment) : sha256('');
    result.compact_composer_visible = Boolean(result.checkpoints.compact.composer);
    result.compact_horizontal_overflow = result.checkpoints.compact.viewport.horizontal_overflow;
    result.verdict = result.expected_response_fragment_present && result.compact_composer_visible && result.compact_horizontal_overflow === 0
      ? 'UNAUTHENTICATED_MOBILE_CHAT_PASS'
      : 'UNAUTHENTICATED_MOBILE_CHAT_NEEDS_REVIEW';
  }
} catch (error) {
  result.verdict = 'INSTRUMENTATION_OR_PRODUCT_FLOW_ERROR';
  result.error = { name: error?.name || 'Error', message: error?.message || String(error), stack_sha256: sha256(error?.stack || '') };
}

result.runtime = {
  console_signals: consoleSignals,
  page_errors: pageErrors,
  failed_first_party_requests: failedRequests,
  first_party_http_error_responses: errorResponses,
};

await browser.close();
fs.writeFileSync(path.join(outputDir, 'chatgpt-unauth-mobile-chat-result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
const summary = `# ChatGPT unauthenticated mobile-chat journey\n\nCase: \`${config.case_id}\`\nVerdict: \`${result.verdict}\`\n\n- Prompt submissions: ${result.prompt_submission_count}\n- Streaming observed: ${Boolean(result.stream_observed)}\n- Completion observed: ${Boolean(result.completion_observed)}\n- Expected response visible: ${Boolean(result.expected_response_fragment_present)}\n- Compact composer visible: ${Boolean(result.compact_composer_visible)}\n- Compact overflow: ${result.compact_horizontal_overflow ?? 'unknown'}\n- Page errors: ${pageErrors.length}\n- First-party HTTP error responses: ${errorResponses.length}\n`;
fs.writeFileSync(path.join(outputDir, 'chatgpt-unauth-mobile-chat-summary.md'), summary, 'utf8');
console.log(summary);
