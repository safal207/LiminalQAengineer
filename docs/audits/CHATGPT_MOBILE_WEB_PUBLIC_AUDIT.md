# ChatGPT mobile-web public audit

**Case:** `chatgpt-mobile-web-public-2026-07-21`  
**Verdict:** `ONE_P3_DIAGNOSTIC_ONLY`  
**Target:** `https://chatgpt.com/`  
**Mode:** passive, public, signed-out web observation

## Executive result

The public ChatGPT mobile-web entry passed the bounded baseline:

- all five user-agent/viewport profiles returned HTTP `200`;
- no horizontal overflow was detected;
- the composer remained visible at `412×915` and compact `412×520` height;
- primary mobile controls for sidebar, login, attachments, dictation and send exposed `44×44` CSS-pixel boxes;
- the mobile login page retained provider, email and Continue choices without horizontal overflow;
- public-home CLS remained between `0` and `0.0004`;
- no home-page console or uncaught runtime error was observed under the primary mobile profile;
- mobile event POSTs received successful HTTP `200/204` responses.

The audit confirmed that ChatGPT serves a distinct signed-out mobile-web branch based on mobile user-agent, not viewport alone. That is an architectural observation, not a defect.

One repeated low-severity diagnostic remains: the mobile login page emits an opaque first-party `console.error`, while the visible login state remains complete and no user-task failure is established.

## Exact evidence

### Baseline matrix

- Repository: `safal207/LiminalQAengineer`
- PR: `#106`
- Exact audited head: `6d77761f2f224afc8983660bcf095a39a243c385`
- Workflow run: `29783360123`
- Artifact: `chatgpt-mobile-web-public-29783360123`
- Artifact SHA-256: `1be5ceda6b73ff4a92ff13fc793c22366a05c97069392ad2ac0ec4a3c5ae7316`
- Baseline packet SHA-256: `b28f6ad07c93f6ddc7e0105b6ce4a9f773763957228d2e7f1dd9361ca7fa1a00`

### Focused diagnostic

- Exact diagnostic head: `e56e2e86770e4ed198380800d970a7198020d6e1`
- Workflow run: `29783766882`
- Artifact: `chatgpt-mobile-web-diagnostics-29783766882`
- Artifact SHA-256: `dc76eadf08f34a03273f95aee2ff3a7256b39c1a600af5cef91c0c0fd799056c`
- Diagnostic packet SHA-256: `545480af7621ee11a7c7bbaaca65c2d134791abab43cddddb1ae0a39a2357434`

Machine-readable adjudications:

- `audits/chatgpt/mobile-web-public-result.json`
- `audits/chatgpt/mobile-web-diagnostics-result.json`

## Product boundary

This audit is specifically about **mobile web** in a browser. It does not treat the ChatGPT Android or iOS **mobile application** as the same product surface.

Official OpenAI documentation establishes that ChatGPT is offered through the web and separate mobile applications, that some signed-out functionality varies by region, and that some capabilities have platform-specific availability. These statements provide context only; they are not evidence that the current mobile-web interface passes or fails.

## Evidence labels

- `SIGNED_OUT_PUBLIC_EVIDENCE` — reproduced on public signed-out pages with exact profile and artifact.
- `CONFIRMED_ARCHITECTURE_NOT_DEFECT` — delivery difference is proven but no user failure follows automatically.
- `CONFIRMED_DIAGNOSTIC_USER_IMPACT_UNKNOWN` — stable diagnostic signal without a demonstrated broken task.
- `REJECTED_FALSE_NETWORK_FAILURE` — successful HTTP delivery was incorrectly grouped as a failed request by the generic detector.
- `REJECTED_FALSE_POSITIVE` — detector output contradicted by screenshot or structural review.
- `NEEDS_AUTHENTICATED_MOBILE_EVIDENCE` — cannot be claimed from signed-out pages.
- `APP_ONLY_OR_PLATFORM_SPECIFIC` — official documentation distinguishes the capability from mobile web.
- `UNKNOWN` — evidence is insufficient.

## Safety boundary

The observers:

- open only `https://chatgpt.com/` and `https://chatgpt.com/auth/login`;
- use desktop/mobile user-agent and viewport combinations;
- capture rendered text, accessible names, focus order, geometry, performance entries, console signals and screenshots;
- repeat bounded states twice;
- do not bypass a challenge or access control.

No prompt is submitted. No login is submitted. No account is accessed. No file is uploaded. No microphone or camera permission is requested. No application API is called directly. No fuzzing, load test, active security test or private-data collection occurs.

## Controlled matrix

| Profile | User-agent | Viewport | Result |
|---|---|---:|---|
| `desktop-ua-desktop-viewport` | Desktop | 1440×900 | HTTP 200; desktop signed-out experience |
| `desktop-ua-mobile-viewport` | Desktop | 412×915 | HTTP 200; responsive desktop branch |
| `mobile-ua-desktop-viewport` | Android mobile | 1440×900 | HTTP 200; mobile-user-agent branch on a wide viewport |
| `mobile-ua-mobile-viewport` | Android mobile | 412×915 | HTTP 200; primary mobile-web state |
| `mobile-ua-compact-height` | Android mobile | 412×520 | HTTP 200; composer and CTA visible |

The matrix separates user-agent routing from viewport-driven responsive behaviour. It does not emulate every Android browser, safe-area inset, browser chrome, real virtual keyboard or OEM skin.

## Confirmed passes

### Public availability and routing — `PASS`

All five home profiles returned HTTP `200` and remained on `https://chatgpt.com/`. The mobile login target also returned HTTP `200`.

### Horizontal layout — `PASS`

No horizontal document overflow was detected in any profile or round.

### Primary mobile controls — `PASS_WITH_CONTEXT`

Under Android mobile user-agent at `412×915`, these visible controls exposed `44×44` or larger boxes:

- Open sidebar;
- Log in;
- Add files and more;
- Start dictation;
- Send message.

The generic detector also flagged the inner textarea content box, a `36`-pixel-high suggestion CTA and legal links. Those counts are not automatic accessibility failures: the textarea sits inside a larger composer container, and links require standards-aware spacing and context review.

### Compact-height layout — `PASS_WITH_BOUNDARY`

At `412×520`, the title, primary composer, dictation/send controls and `What can I do?` CTA remained visible with no horizontal overflow. This does not prove behaviour with a real virtual keyboard because no keyboard was opened.

### Mobile login layout — `PASS`

At `412×915`, the login page displayed provider choices, email input, Continue and Try it first. Main provider and Continue controls measured `340×44` CSS pixels, with no horizontal overflow.

### Layout stability — `PASS_IN_OBSERVATION_WINDOW`

Observed CLS ranged from `0` to `0.0004` across the public profiles.

### Mobile event delivery — `PASS_WITH_DETECTOR_CORRECTION`

The generic observer initially labelled six `/unauth-mweb/events/` POSTs as aborted. The focused run proved that the first-party endpoints returned successful responses before the browser loading signal:

- page view: HTTP `204`;
- performance: HTTP `204`;
- business: HTTP `204`;
- stats flush: HTTP `200`.

The successful response preceded the `net::ERR_ABORTED` CDP/Puppeteer signal by `0–33 ms`. No `visibilitychange`, `pagehide`, `beforeunload` or `unload` event occurred before capture.

**Adjudication:** `REJECTED_FALSE_NETWORK_FAILURE`. The generic detector must not count a successful `2xx` response followed by loading-aborted as failed delivery without additional evidence.

## Confirmed architecture

### Mobile user-agent selects a distinct public branch — `CONFIRMED_ARCHITECTURE_NOT_DEFECT`

At the same `412×915` viewport:

| Desktop user-agent | Android mobile user-agent |
|---|---|
| Heading: `What’s on the agenda today?` | Heading: `Where should we begin?` |
| Header includes a model selector | Header uses a centred ChatGPT label |
| No visible `What can I do?` CTA in the captured state | `What can I do?` CTA visible |
| Desktop/responsive delivery | Event namespace includes `/unauth-mweb/events/` |

This proves a separate mobile-web branch. It is not a defect by itself. Fixes, accessibility reviews and experiments must cover mobile user-agent behaviour instead of relying on viewport-only responsive testing.

## Remaining diagnostic

### Opaque first-party console error on mobile login — `CONFIRMED_DIAGNOSTIC_USER_IMPACT_UNKNOWN`

The mobile login page emitted one stable `console.error` in both focused rounds:

- elapsed after navigation: approximately `1.0–1.3 s`;
- console text: `JSHandle@error`;
- serialized values: empty object and `undefined`;
- first-party source: `2340486e-dndlwhxa5s7p8x6d.js`, line `27`, column `11836`;
- no uncaught page error;
- no visible login failure;
- provider choices, email field and Continue remained present.

**Classification:** `P3-diagnostic`. The signal may represent noisy or intentionally caught logging, but its semantic cause cannot be established from public minified assets. It is not a security claim and not proof that login is broken.

Recommended first-party repair path: resolve the stack through source maps and emit an explicit error code/message if logging is intentional, then rerun the public console-cleanliness check.

## Rejected detector outputs

### Composer overlap — `REJECTED_FALSE_POSITIVE`

Screenshot review showed no obstruction. The detected fixed/sticky surface was an ancestor container containing the composer. The geometry detector must exclude ancestor/descendant pairs.

### Duplicate visible heading — `REJECTED_BY_BROWSER_MATRIX`

A text-only public fetch suggested repeated start-state wording. The controlled browser matrix found no duplicate visible heading in any profile.

### Raw small-target count — `ADJUDICATED_NOT_A_CONFIRMED_DEFECT`

Critical icon controls met the `44×44` target in the tested mobile state. Suggestion and legal-link geometry still deserve standards-aware review, but the raw detector count is not a defect verdict.

## Authenticated journeys outside this packet

The following remain `NEEDS_AUTHENTICATED_MOBILE_EVIDENCE`:

1. long conversation scrolling and return-to-latest behaviour;
2. streaming response, stop/regenerate and interruption recovery;
3. composer expansion with multiple lines and a real virtual keyboard;
4. attachments, camera, images and file-preview states;
5. sidebar history, chat search, Projects, pinned chats and deep links;
6. model/tool selection and plan-limit messaging;
7. Search citations, widgets and source panels;
8. custom GPTs, Deep research, Work and availability by plan;
9. settings, memory, privacy controls, billing and workspace switching;
10. error recovery after offline/online transitions;
11. cross-device draft/history synchronisation;
12. accessibility with TalkBack, browser zoom and external keyboard.

A platform availability difference is not automatically a UX defect. Each authenticated conclusion requires an authorised test account, exact plan/workspace, browser version, region and state trace.

## Next bounded tests

1. Run an authorised signed-in account matrix for long chat, streaming, attachments, sidebar history and offline recovery.
2. Run a real Android Chrome session with virtual keyboard and `visualViewport` evidence.
3. Run TalkBack, external-keyboard and `200%` browser-zoom tasks.
4. Re-run the public login console probe after the relevant first-party bundle changes.

## Decision rule

A detector signal becomes a public mobile-web finding only when:

1. it repeats under the exact profile or controlled matrix;
2. visibility and user impact are confirmed from screenshot or task evidence;
3. mobile web is isolated from desktop web and native apps;
4. expected signed-out, telemetry or regional behaviour is excluded;
5. exact-run evidence is preserved;
6. uncertainty remains explicit.

`ONE_P3_DIAGNOSTIC_ONLY` does not authorise external reporting, account access, security claims, deployment or merge. Human review remains required before any external use.

## Official public references

- ChatGPT FAQ: `https://help.openai.com/en/articles/12677804-what-is-chatgpt-faq`
- ChatGPT home page: `https://help.openai.com/en/articles/9125172-the-chatgpt-home-page`
- Login troubleshooting: `https://help.openai.com/en/articles/7426629-why-cant-i-log-in-to-chatgpt`
- ChatGPT capabilities overview: `https://help.openai.com/en/articles/9260256-chatgpt-capabilities-overview`
- File uploads FAQ: `https://help.openai.com/en/articles/8555545-file-uploads-faq`
- Canvas availability: `https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it`
- Voice FAQ: `https://help.openai.com/en/articles/8400625-voice-mode`
