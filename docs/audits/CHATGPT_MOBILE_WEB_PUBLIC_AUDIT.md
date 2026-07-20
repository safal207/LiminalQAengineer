# ChatGPT mobile-web public audit

**Case:** `chatgpt-mobile-web-public-2026-07-21`  
**Verdict:** `HUMAN_REVIEW_REQUIRED`  
**Target:** `https://chatgpt.com/`  
**Mode:** passive, public, signed-out web observation

## Question

Does ChatGPT mobile web preserve a clear path from arrival to first prompt while keeping navigation, composer state, authentication choices, accessibility semantics and compact-height recovery understandable on a small screen?

## Product boundary

This audit is specifically about **mobile web** in a browser. It does not treat the ChatGPT Android or iOS **mobile application** as the same product surface.

Official OpenAI documentation establishes that:

- ChatGPT is available on the web at `chatgpt.com` and in separate iOS and Android applications;
- signed-out web use may be available in supported regions, while availability can vary by region;
- file uploads are available on supported paid plans on web and mobile apps;
- some capabilities have platform-specific boundaries: for example, Canvas documentation states that mobile web support is still coming soon;
- Voice documentation distinguishes desktop web availability from mobile-app availability for some voice experiences;
- login can be affected by browser, cookie, JavaScript, network and Cloudflare conditions.

These official capability statements are context, not proof that the current mobile-web interface succeeds or fails.

## Evidence labels

- `SIGNED_OUT_PUBLIC_EVIDENCE` — reproduced on public signed-out pages with exact profile and artifact.
- `REPEATED_PUBLIC_OBSERVATION` — reproduced in both bounded rounds for the same profile and target.
- `USER_IMPACT_UNKNOWN` — signal exists but no user-task failure has been established.
- `NEEDS_SCREENSHOT_REVIEW` — geometry detector requires visual human confirmation.
- `NEEDS_AUTHENTICATED_MOBILE_EVIDENCE` — cannot be claimed from signed-out pages.
- `APP_ONLY_OR_PLATFORM_SPECIFIC` — official documentation distinguishes the capability from mobile web.
- `UNKNOWN` — evidence is insufficient.

## Safety boundary

The observer:

- opens only `https://chatgpt.com/` and `https://chatgpt.com/auth/login`;
- uses desktop/mobile user-agent and viewport combinations;
- captures rendered text, headings, accessible names, focus order, layout geometry, performance entries, console signals and screenshots;
- repeats each bounded profile twice;
- does not bypass a challenge or access control.

No prompt is submitted. No login is submitted. No account is accessed. No file is uploaded. No microphone or camera permission is requested. No application API is called directly. No fuzzing, load test, active security test or private-data collection occurs.

## Controlled matrix

| Profile | User-agent | Viewport | Purpose |
|---|---|---:|---|
| `desktop-ua-desktop-viewport` | Desktop | 1440×900 | Desktop baseline |
| `desktop-ua-mobile-viewport` | Desktop | 412×915 | Isolate responsive layout |
| `mobile-ua-desktop-viewport` | Android mobile | 1440×900 | Isolate user-agent routing |
| `mobile-ua-mobile-viewport` | Android mobile | 412×915 | Primary mobile-web state |
| `mobile-ua-compact-height` | Android mobile | 412×520 | Approximate compact browser/keyboard pressure without opening a keyboard |

The matrix distinguishes user-agent routing from viewport-driven responsive behaviour. It does not emulate every Android browser, browser chrome, safe-area inset, virtual keyboard or OEM skin.

## Public detectors

### Route and state

- HTTP status and final URL;
- title, language and body-text digest;
- desktop/mobile user-agent divergence;
- challenge or error state without attempting bypass.

### Responsive layout

- horizontal document overflow;
- visible composer candidates;
- fixed/sticky geometry and possible overlap;
- compact-height visibility;
- screenshot evidence.

### Interaction clarity

- visible interactive controls and accessible names;
- touch-target geometry below `44×44` CSS pixels;
- first 18 keyboard-focus stops;
- duplicate visible headings.

A small target detector is not an automatic accessibility failure: inline links and nested controls require context and screenshot review.

### Runtime and delivery

- console errors and uncaught exceptions;
- first-party failed requests and HTTP `4xx/5xx` responses;
- navigation/resource transfer summaries;
- CLS and long-task observations where browser APIs expose them.

Runtime signals remain `USER_IMPACT_UNKNOWN` until tied to a visible broken task.

## Public semantic baseline

The public page currently exposes a signed-out value proposition, login/signup actions and a prompt entry state. A text-only public fetch also exposes repeated start-state wording and navigation labels, but that evidence is not sufficient to call a mobile-web defect because it does not isolate viewport, user-agent, visibility or accessibility-tree state.

The GitHub browser matrix is the deciding evidence source for this packet.

## Authenticated journeys outside this packet

The following remain `NEEDS_AUTHENTICATED_MOBILE_EVIDENCE`:

1. long conversation scrolling and return-to-latest behaviour;
2. streaming response, stop/regenerate and interruption recovery;
3. composer expansion with multiple lines and a real virtual keyboard;
4. attachments, camera, images and file-preview states;
5. sidebar history, chat search, Projects, pinned chats and deep links;
6. model/tool selection and plan-limit messaging;
7. Search citations, widgets and source panels;
8. custom GPTs, Plugins, Deep research, Work and availability by plan;
9. settings, memory, privacy controls, billing and workspace switching;
10. error recovery after offline/online transitions;
11. cross-device draft/history synchronisation;
12. accessibility with TalkBack, browser zoom and external keyboard.

Official documentation also identifies platform differences. For example, Canvas is documented for web desktop while mobile platforms, including mobile web, are still listed as coming soon. Such a gap is a product capability boundary, not automatically a UX defect.

## Human-review questions

After the run, review:

- Does mobile user-agent receive a materially different route or state from a mobile viewport alone?
- Is the primary composer visible and unobstructed at normal and compact height?
- Are duplicate headings actually visible, or are they implementation/accessibility duplicates?
- Are controls below 44 CSS pixels isolated inline links or critical icon buttons?
- Are first-party failures expected signed-out/telemetry behaviour or a broken user-facing resource?
- Does the focus sequence reach skip navigation, menu, login, composer and legal links in a comprehensible order?

## Product hypotheses for later authenticated audit

These are not findings:

- A long mobile conversation may create excessive scroll distance and context loss.
- The composer may compete with browser chrome, virtual keyboard, attachment tray and generated widgets.
- Tool/model controls may become crowded as mobile-web capability breadth grows.
- Recovery may be unclear when a stream is interrupted or a draft becomes stale across devices.
- Desktop-first rich surfaces may require an explicit mobile fallback instead of silent omission.

Each requires an authorised test account, exact plan/workspace, browser version, region and screenshot/state trace.

## Decision rule

A detector signal becomes a public mobile-web finding only when:

1. it repeats under the exact profile or controlled matrix;
2. visibility and user impact are confirmed from screenshot or task evidence;
3. mobile web is isolated from desktop web and native apps;
4. expected signed-out or regional behaviour is excluded;
5. exact-run evidence is preserved;
6. uncertainty remains explicit.

`HUMAN_REVIEW_REQUIRED` does not authorise external reporting, account access, security claims, deployment or merge.

## Official public references

- ChatGPT FAQ: `https://help.openai.com/en/articles/12677804-what-is-chatgpt-faq`
- ChatGPT home page: `https://help.openai.com/en/articles/9125172-the-chatgpt-home-page`
- Login troubleshooting: `https://help.openai.com/en/articles/7426629-why-cant-i-log-in-to-chatgpt`
- ChatGPT capabilities overview: `https://help.openai.com/en/articles/9260256-chatgpt-capabilities-overview`
- File uploads FAQ: `https://help.openai.com/en/articles/8555545-file-uploads-faq`
- Canvas availability: `https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it`
- Voice FAQ: `https://help.openai.com/en/articles/8400625-voice-mode`
