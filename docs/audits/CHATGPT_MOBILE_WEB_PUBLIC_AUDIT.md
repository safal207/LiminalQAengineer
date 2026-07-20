# ChatGPT mobile-web public audit

**Case:** `chatgpt-mobile-web-public-2026-07-21`  
**Verdict:** `ESCALATE_BOUNDED_FOLLOW_UP`  
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
- no home-page console or uncaught runtime error was observed under the primary mobile profile.

The audit confirmed that ChatGPT serves a distinct signed-out mobile-web branch based on mobile user-agent, not viewport alone. That is an architectural observation, not a defect.

Two repeated diagnostic signals require narrower follow-up before any external report:

1. mobile-only event POST requests under `/unauth-mweb/events/` were aborted around the bounded lifecycle;
2. the mobile login page emitted one opaque `JSHandle@error` console signal in each round.

Neither signal has demonstrated user impact.

## Exact evidence

- Repository: `safal207/LiminalQAengineer`
- PR: `#106`
- Exact audited head: `6d77761f2f224afc8983660bcf095a39a243c385`
- Workflow run: `29783360123`
- Artifact: `chatgpt-mobile-web-public-29783360123`
- Artifact SHA-256: `1be5ceda6b73ff4a92ff13fc793c22366a05c97069392ad2ac0ec4a3c5ae7316`
- Result-packet SHA-256: `b28f6ad07c93f6ddc7e0105b6ce4a9f773763957228d2e7f1dd9361ca7fa1a00`
- Machine adjudication: `audits/chatgpt/mobile-web-public-result.json`

## Question

Does ChatGPT mobile web preserve a clear path from arrival to first prompt while keeping navigation, composer state, authentication choices, accessibility semantics and compact-height recovery understandable on a small screen?

## Product boundary

This audit is specifically about **mobile web** in a browser. It does not treat the ChatGPT Android or iOS **mobile application** as the same product surface.

Official OpenAI documentation establishes that:

- ChatGPT is available on the web at `chatgpt.com` and in separate iOS and Android applications;
- signed-out web use may be available in supported regions, while availability can vary by region;
- file uploads are available on supported paid plans on web and mobile apps;
- some capabilities have platform-specific boundaries: Canvas documentation still lists mobile platforms, including mobile web, as coming soon;
- Voice documentation distinguishes desktop web from mobile-app availability for some voice experiences;
- login can be affected by browser, cookies, JavaScript, network and Cloudflare conditions.

These official capability statements are context, not proof that the current mobile-web interface succeeds or fails.

## Evidence labels

- `SIGNED_OUT_PUBLIC_EVIDENCE` — reproduced on public signed-out pages with exact profile and artifact.
- `REPEATED_PUBLIC_OBSERVATION` — reproduced in both bounded rounds for the same profile and target.
- `CONFIRMED_ARCHITECTURE_NOT_DEFECT` — delivery difference is proven but no user failure follows automatically.
- `USER_IMPACT_UNKNOWN` — signal exists but no user-task failure has been established.
- `REJECTED_FALSE_POSITIVE` — detector output contradicted by screenshot or structural review.
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

| Profile | User-agent | Viewport | Result |
|---|---|---:|---|
| `desktop-ua-desktop-viewport` | Desktop | 1440×900 | HTTP 200; desktop signed-out experience |
| `desktop-ua-mobile-viewport` | Desktop | 412×915 | HTTP 200; responsive desktop branch |
| `mobile-ua-desktop-viewport` | Android mobile | 1440×900 | HTTP 200; mobile-user-agent branch expanded to wide viewport |
| `mobile-ua-mobile-viewport` | Android mobile | 412×915 | HTTP 200; primary mobile-web state |
| `mobile-ua-compact-height` | Android mobile | 412×520 | HTTP 200; composer and CTA visible |

The matrix distinguishes user-agent routing from viewport-driven responsive behaviour. It does not emulate every Android browser, browser chrome, safe-area inset, real virtual keyboard or OEM skin.

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

The generic detector also flagged the inner textarea content box, a `36`-pixel-high suggestion CTA and legal links. Those raw counts are not an automatic accessibility failure: the textarea sits inside a larger composer container, and links require standards-aware spacing and context review.

### Compact-height layout — `PASS_WITH_BOUNDARY`

At `412×520`, the title, primary composer, dictation/send controls and `What can I do?` CTA remained visible with no horizontal overflow. This does not prove behaviour with a real virtual keyboard because no keyboard was opened.

### Mobile login layout — `PASS`

At `412×915`, the login page displayed:

- Continue with Google;
- Continue with Apple;
- Continue with phone;
- Email address;
- Continue;
- Try it first.

The main provider and Continue controls measured `340×44` CSS pixels and no horizontal overflow was observed.

### Layout stability — `PASS_IN_OBSERVATION_WINDOW`

Observed CLS ranged from `0` to `0.0004` across the public profiles.

## Confirmed architecture

### Mobile user-agent selects a distinct public branch — `CONFIRMED_ARCHITECTURE_NOT_DEFECT`

At the same `412×915` viewport:

| Desktop user-agent | Android mobile user-agent |
|---|---|
| Heading: `What’s on the agenda today?` | Heading: `Where should we begin?` |
| Header includes a model selector | Header uses a centred ChatGPT label |
| No visible `What can I do?` CTA in the captured state | `What can I do?` CTA visible |
| Desktop/responsive delivery | Event namespace includes `/unauth-mweb/events/` |

This proves a separate mobile-web branch. It is not a defect by itself. It means fixes, accessibility reviews and experiments must cover mobile user-agent behaviour rather than relying on viewport-only responsive testing.

## Diagnostic signals requiring follow-up

### Mobile event POST aborts — `REPEATED_USER_IMPACT_UNKNOWN`

Each mobile-user-agent home run recorded six aborted POST requests under:

- `/unauth-mweb/events/page-view`;
- `/unauth-mweb/events/performance`;
- `/unauth-mweb/events/business`;
- `/unauth-mweb/events/statsc/flush`.

The requests are event/telemetry routes, and the bounded browser closes after evidence capture. No missing content, HTTP error response or visible user failure was observed. This must not be reported as a product defect until a lifecycle trace proves that requests fail before teardown or that required analytics are lost.

### Opaque login console signal — `REPEATED_USER_IMPACT_UNKNOWN`

The mobile login page emitted one console error represented as `JSHandle@error` in both rounds. The current observer did not serialize the underlying object, and the login form remained visibly complete. A focused diagnostic run must preserve console arguments and stack information before any defect claim.

## Rejected detector outputs

### Composer overlap — `REJECTED_FALSE_POSITIVE`

The generic geometry detector reported overlap between the composer and a fixed/sticky surface. Screenshot review showed no obstruction: the detected surface was an ancestor layout container containing the composer. Future detector revisions must exclude ancestor/descendant pairs.

### Duplicate visible heading — `REJECTED_BY_BROWSER_MATRIX`

A text-only public fetch suggested repeated start-state wording. The controlled browser matrix found no duplicate visible heading in any profile. The text-only signal is not a defect.

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

## Next bounded tests

1. Serialize login console arguments and stacks without submitting credentials.
2. Trace `visibilitychange`, `pagehide` and teardown timing for `/unauth-mweb/events/`.
3. Run a real Android Chrome session with virtual keyboard and `visualViewport` evidence.
4. Run an authorised signed-in account matrix for long chat, streaming, attachments, sidebar history and offline recovery.
5. Run TalkBack, external-keyboard and `200%` browser-zoom tasks.

## Decision rule

A detector signal becomes a public mobile-web finding only when:

1. it repeats under the exact profile or controlled matrix;
2. visibility and user impact are confirmed from screenshot or task evidence;
3. mobile web is isolated from desktop web and native apps;
4. expected signed-out, telemetry or regional behaviour is excluded;
5. exact-run evidence is preserved;
6. uncertainty remains explicit.

`ESCALATE_BOUNDED_FOLLOW_UP` does not authorise external reporting, account access, security claims, deployment or merge.

## Official public references

- ChatGPT FAQ: `https://help.openai.com/en/articles/12677804-what-is-chatgpt-faq`
- ChatGPT home page: `https://help.openai.com/en/articles/9125172-the-chatgpt-home-page`
- Login troubleshooting: `https://help.openai.com/en/articles/7426629-why-cant-i-log-in-to-chatgpt`
- ChatGPT capabilities overview: `https://help.openai.com/en/articles/9260256-chatgpt-capabilities-overview`
- File uploads FAQ: `https://help.openai.com/en/articles/8555545-file-uploads-faq`
- Canvas availability: `https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it`
- Voice FAQ: `https://help.openai.com/en/articles/8400625-voice-mode`
