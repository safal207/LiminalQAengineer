# ChatGPT authenticated mobile-web capture

**Case:** `chatgpt-authenticated-mobile-web-2026-07-21`  
**Status:** `PENDING_AUTHORIZED_LOCAL_EVIDENCE`  
**Parent public audit:** LiminalQA PR `#106` at `2407be212e19a393fcd0d8dd33d9fe444aea663b`

## Purpose

The public signed-out audit established a clean baseline and one low-severity login-console diagnostic. It could not answer the product questions that matter inside a real signed-in mobile chat:

- long-thread navigation and return-to-latest;
- streaming, stop and recovery;
- composer growth with a real virtual keyboard;
- attachment tray and file-preview entry;
- sidebar/history, Search sources, widgets and other rich surfaces;
- offline and reconnect behaviour;
- browser zoom and assistive-technology boundaries.

This packet creates a **local-only evidence capture kit**. It attaches to a Chrome tab that the user has already opened and signed into. It does not receive credentials, export cookies, save storage state, submit prompts automatically or persist raw conversation text.

## Trust boundary

The observer is intentionally unable to:

- navigate to a login page;
- enter email, password or one-time codes;
- export cookies, local storage or browser profiles;
- click controls;
- type or submit prompts;
- select or upload files;
- request microphone or camera permission;
- capture request or response bodies;
- call private application APIs directly;
- bypass access controls;
- run in GitHub Actions with a private session.

Every product action is performed manually by the account owner. The script records a checkpoint only after the user presses Enter in the local terminal.

## Privacy model

Persisted evidence contains:

- viewport and `visualViewport` geometry;
- scroll positions and distance to the latest content;
- composer geometry and draft length;
- message count, role, text length and SHA-256 digest;
- allowlisted control names such as `send`, `stop`, `attachment` and `sidebar`;
- hashes rather than unknown control text;
- first-party status/failure metadata without request or response bodies;
- console/page-error hashes rather than raw text;
- CLS and long-task observations after attachment.

It does **not** persist:

- message text;
- chat titles;
- account name or email;
- full conversation URLs or IDs;
- prompt contents;
- credentials, cookies or tokens;
- network bodies.

Screenshots are disabled by default. When explicitly enabled, the script temporarily makes all text transparent and blurs images, SVG, canvas, video and iframe content. This is a best-effort geometry record, not a guarantee that every custom-rendered surface is anonymous. Review screenshots locally before sharing them.

## Real Android Chrome setup

Chrome's official remote-debugging workflow supports connecting desktop DevTools to Chrome on an Android device through USB debugging. A direct CDP forward can expose the device's Chrome target on local port `9222`.

1. Enable Android Developer options and USB debugging.
2. Open Chrome on the Android device.
3. Open `https://chatgpt.com/`, sign in manually and select a dedicated non-sensitive test chat.
4. Connect the device to the computer and approve the debugging prompt on the device.
5. Verify the device:

```bash
adb devices -l
```

6. Forward the Chrome DevTools socket:

```bash
adb forward tcp:9222 localabstract:chrome_devtools_remote
```

7. Confirm that local targets are visible:

```bash
curl http://127.0.0.1:9222/json
```

Official Chrome reference:

- `https://developer.chrome.com/docs/devtools/remote-debugging`

## Install the local driver

From the repository working tree at this branch:

```bash
npm install --no-save --package-lock=false puppeteer-core@24.16.0
```

The package is only a CDP client. It does not launch a new authenticated browser or copy a profile.

## Run without screenshots

```bash
node scripts/chatgpt_authenticated_mobile_web_capture.mjs \
  --browser-url http://127.0.0.1:9222 \
  --config audits/chatgpt/authenticated-mobile-web-capture-v1.json \
  --output-dir reports/chatgpt-authenticated-mobile-web
```

If more than one `chatgpt.com` tab is open, close the extras or pass an explicit zero-based `--page-index`.

## Optional redacted screenshots

```bash
node scripts/chatgpt_authenticated_mobile_web_capture.mjs \
  --browser-url http://127.0.0.1:9222 \
  --config audits/chatgpt/authenticated-mobile-web-capture-v1.json \
  --output-dir reports/chatgpt-authenticated-mobile-web \
  --include-screenshots \
  --acknowledge-private-screenshot-risk
```

Do not commit screenshots or evidence from private chats. Use a dedicated benign test thread.

## User-driven checkpoint sequence

### 1. `idle-long-chat`

Open a long thread and stop near its middle.

Observe:

- available scroll containers;
- distance from the latest content;
- whether the composer remains stable;
- whether a return-to-latest control is present;
- message count and geometry without message text.

### 2. `return-to-latest`

Use the visible product control to return to the newest turn.

Observe:

- final distance to bottom;
- focus movement;
- whether the newest assistant action controls remain reachable;
- unexpected layout shift.

### 3. `composer-multiline-keyboard-open`

Place a benign multi-line draft in the composer and keep the real Android keyboard open. Do not submit at this checkpoint.

Observe:

- `visualViewport` height and offset;
- composer rectangle;
- inferred keyboard state;
- horizontal overflow;
- fixed/sticky surfaces that may compete with the composer;
- send/attachment/dictation reachability.

### 4. `streaming-active`

In a dedicated test chat, manually submit a benign prompt and capture while the response is streaming.

Observe:

- stop control visibility;
- scroll anchoring;
- composer availability;
- runtime and network metadata;
- long tasks and CLS after attachment.

### 5. `stream-stopped-or-complete`

Stop the response manually or let it finish.

Observe:

- stop-to-recovery transition;
- regenerate/retry controls;
- duplicate or missing assistant turn geometry;
- retained draft and scroll position.

### 6. `attachment-tray-open`

Open the tray without selecting a file.

Observe:

- tray/dialog geometry;
- composer visibility;
- keyboard interaction;
- exit and recovery path.

### 7. `sidebar-history-open`

Open the sidebar while staying in the benign test thread.

Observe:

- overlay and focus state;
- close path;
- current-thread continuity;
- viewport and composer displacement.

Chat titles are not persisted by the observer.

### 8. `search-widget-or-source-panel`

Open a non-sensitive Search source panel or widget when available to the account and plan.

Observe:

- panel width and overflow;
- return path to the conversation;
- source controls and scrolling;
- composer continuity.

### 9–10. `offline` and `recovered-online`

Use DevTools network controls to go offline, then restore connectivity.

Observe:

- explicit offline state;
- draft retention;
- failed-request metadata;
- recovery without duplicate submission;
- whether stale streaming or send state remains.

### 11. `browser-zoom-200`

Use the intended browser zoom or accessibility text-scaling state.

Observe:

- horizontal overflow;
- composer and primary-control reachability;
- dialog/sidebar clipping;
- source or attachment-panel recovery.

## Evidence output

The output directory contains one JSON file for each captured checkpoint and a final `manifest.json`.

The manifest verdict remains:

```text
AUTHENTICATED_LOCAL_EVIDENCE_CAPTURED_PENDING_ADJUDICATION
```

A checkpoint signal is not a product defect until:

1. it repeats on an exact device/browser/account-plan state;
2. the failed user task is explicit;
3. private-text redaction is verified;
4. a desktop or native-app comparison is not silently substituted for mobile web;
5. expected plan, region or platform capability boundaries are excluded;
6. Pythia judges the claim before CML and LS preserve or prioritise it.

## Current official capability context

OpenAI's current public help material should be treated as capability context, not pass/fail evidence:

- file uploads are documented for supported plans on `chatgpt.com` and mobile apps;
- Voice availability depends on product surface, plan, region and rollout state;
- Canvas documentation currently lists mobile platforms, including mobile web, as coming soon.

References:

- `https://help.openai.com/en/articles/8555545-file-uploads-faq`
- `https://help.openai.com/en/articles/20001274`
- `https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it`

The audit records what the exact account and browser expose. It must not assume feature parity from documentation alone.

## Handoff after capture

After the local capture is reviewed and explicitly selected for sharing:

```text
LiminalQA exact evidence
→ Pythia claim judgment
→ CML canonical memory
→ LS human-impact scorecard
```

Until a manifest and checkpoint artifacts exist, downstream verdict is:

```text
PENDING_AUTHORIZED_LOCAL_EVIDENCE
```

No external report, security claim, deployment, delivery or merge is authorised.
