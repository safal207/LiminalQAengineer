# Starbucks Public Lotus Audit v0.1

## Decision

This audit converts the first passive Starbucks review into the same bounded LiminalQA → Pythia → CML → LS → LiminalDB path used by the other company audits.

```text
public route observations
+ sanitized private disclosure signal
→ exact public evidence inventory
→ six bounded claims
→ Lotus Decision Packet
→ artifact-only LiminalDB AuditEvents
```

The packet contains:

- 2 `CONFIRMED`;
- 2 `NEEDS_EVIDENCE`;
- 2 `BLOCKED`.

The strongest security signal is deliberately **not** published as a confirmed vulnerability. Its exact routes and underlying material remain outside this public repository pending coordinated disclosure.

## Exact scope

- no authentication or account creation;
- no orders, payments, gift-card, rewards, or profile mutations;
- no credential validation or token requests;
- no direct application API calls;
- no candidate, customer, or account-data access;
- no crawling, fuzzing, load testing, bypass, or exploitation;
- public Starbucks pages and official public statements only.

## Disclosure boundary

```text
private_reference_id = SBX-PRIVATE-SEC-2026-07-19-001
raw_secret_stored = false
raw_secret_used = false
affected_careers_routes_published = false
```

This preserves the existence and judgment state of the signal without turning the public repository into a disclosure channel.

## Evidence inventory

- `audits/lotus/starbucks/starbucks-public-evidence-v0.1.json`
- `audits/lotus/starbucks/starbucks-findings-v0.1.json`

Public surfaces reviewed on 2026-07-19:

- menu;
- store locator;
- sign-in;
- rewards;
- gift cards;
- sitemap;
- Starbucks digital-accessibility statement.

## Lotus result

| ID | Finding | Lotus | Severity | LS risk |
|---|---|---|---|---|
| `SBX-WEB-JS-DEPENDENCY-001` | Five critical routes terminate at a JavaScript-required response for the non-JavaScript text client | `CONFIRMED` | P2 | MEDIUM |
| `SBX-SEO-SITEMAP-DUPLICATES-001` | The sitemap repeats canonical product URLs across category sections | `CONFIRMED` | P3 | LOW |
| `SBX-SEC-PUBLIC-CREDENTIAL-SIGNAL-001` | A credential-like signal exists in private evidence, but the public packet cannot attest it | `NEEDS_EVIDENCE` | UNASSIGNED | HIGH |
| `SBX-A11Y-DUPLICATE-NAV-CANDIDATE-001` | Repeated navigation markup may affect the accessibility tree | `NEEDS_EVIDENCE` | UNASSIGNED | UNKNOWN |
| `SBX-SEC-ACTIVE-EXPLOIT-HYPOTHESIS-001` | The credential-like value is proven active and exploitable | `BLOCKED` | UNASSIGNED | NONE |
| `SBX-A11Y-NOJS-WCAG-HYPOTHESIS-001` | JavaScript dependency alone proves a WCAG violation | `BLOCKED` | UNASSIGNED | NONE |

## Confirmed: critical routes have one terminal degraded state

The bounded non-JavaScript text client received only a JavaScript-required message from:

```text
/menu
/store-locator
/account/signin
/rewards
/gift
```

Causal path:

```text
critical route request
→ application shell requires JavaScript
→ route-specific content and recovery guidance are absent
→ visitor cannot complete the route's read-only purpose in that state
```

This confirms route behavior and resilience risk. It does **not** automatically prove failure in every supported browser or a WCAG conformance violation.

Recommended correction:

1. preserve route identity in the server response;
2. provide meaningful retry or support guidance;
3. expose critical read-only content where practical;
4. keep a non-empty accessible main landmark;
5. test each route under an exact script-failure profile.

## Confirmed: canonical URL duplication in sitemap

The generated sitemap repeats product routes, including examples ending in:

```text
/2122257/single
/2124652/single
```

Likely causal candidate:

```text
product belongs to several menu categories
→ generator appends once per category
→ no final canonical de-duplication pass
→ identical URL is emitted repeatedly
```

Duplicate presence is confirmed. Ranking harm, crawl-budget cost, and direct customer impact are not measured.

## Needs evidence: private credential signal

The initial review observed a populated client-secret field on more than one public careers page. It correctly left exploitability unknown, but comparison with the stronger company audits exposed a publication problem: this public repository does not contain a safe, independently reviewable evidence bundle, while publishing exact routes before rotation could increase risk.

Lotus therefore records:

```text
Pythia: ESCALATE
CML: CONFLICT
LS: HIGH
Decision: NEEDS_EVIDENCE
Severity: UNASSIGNED
```

This is not a low-priority signal. Private disclosure, rotation, and owner-side log review remain urgent. The packet simply refuses to grant a public vulnerability or severity claim without safe evidence.

## Needs evidence: repeated navigation structures

Source duplication may be ordinary responsive markup correctly hidden from focus and the accessibility tree. Required evidence:

- desktop and mobile accessibility trees;
- computed visibility;
- landmark count and accessible names;
- keyboard focus order;
- screen-reader output in a supported environment;
- explicit WCAG success-criterion mapping.

No accessibility severity is assigned before this experiment.

## Blocked claims and negative causal memory

### Active exploitability

The claim that the credential-like value is proven active or grants token, API, or candidate-data access is blocked.

```text
credential validation = not performed
token request = not performed
API request = not performed
data access = not performed
```

The exposure signal remains available for private remediation, but downstream impact is not invented.

### Automatic WCAG failure

The claim that a JavaScript-required response alone proves WCAG A or AA non-conformance is blocked. The route behavior is useful QA evidence; accessibility conformance requires a mapped user task, supported environment, assistive-technology evidence, and a specific success criterion.

## Cross-audit gap review

The first Starbucks report was a useful discovery memo, but it missed controls already present in the stronger company audits.

### 1. Exact evidence lineage

Revolut pins source commits and blobs. Claude pins workflow runs, artifact hashes, raw-result hashes, and exact performance profiles. TakeProfit pins run IDs, screenshots, hold durations, and exact branch heads.

Starbucks still needs:

- response or screenshot SHA-256 values;
- exact timestamps per route;
- browser/client version;
- response status and headers;
- workflow run and artifact IDs.

These are now explicit next-phase requirements rather than assumed evidence.

### 2. Negative memory

Revolut preserves a rejected order-book hypothesis. TakeProfit preserves the rejection of a visible stale-price claim when the chart is not proven to consume the observed transport.

Starbucks now preserves two rejected claims:

- exposure signal ⇒ proven active exploit;
- JavaScript dependency ⇒ automatic WCAG violation.

This prevents future reports from repeatedly upgrading weak evidence.

### 3. Visible state versus implementation signal

TakeProfit separates network ordering from what the visible chart consumes. Tradernet separates first-party lifecycle failures from third-party telemetry.

The Starbucks packet now separates:

- non-JavaScript response behavior;
- supported-browser user experience;
- accessibility-tree behavior;
- security exposure signal;
- credential validity;
- downstream authorization and data impact.

### 4. Temporal experiments

TakeProfit uses independent outage rounds. Claude uses exact reruns and supersedes an earlier measurement conflict. Tradernet checks bootstrap, outage, recovery, reload, and teardown.

Starbucks still needs:

- three fresh contexts per critical route;
- main-bundle failure versus third-party-script controls;
- recovery after scripts return;
- desktop and mobile runs;
- accessibility-tree comparison by breakpoint;
- sitemap comparison across at least two dates;
- a private remediation recheck after credential rotation.

### 5. Supersession rules

Later owner confirmation must create a new event rather than rewrite the original credential observation. A future accessibility run may confirm or reject the navigation candidate. A full-browser result must not overwrite the bounded non-JavaScript result because they describe different system states.

### 6. Data minimization

Revolut runtime probes retain schema shape and hashes rather than raw market values. Tradernet retains normalized URLs and counts rather than payloads. Airbnb requires HAR redaction and screenshot review.

Starbucks follows the same boundary:

- no raw secret;
- no exact affected careers routes in public evidence;
- no cookies, headers, candidate data, or response bodies;
- only public route names, normalized observations, and a private reference.

## Next bounded experiments

### Public route resilience matrix

For each critical route:

1. open a fresh browser context;
2. capture a normal baseline;
3. block the main first-party JavaScript bundle;
4. block third-party scripts only as a control;
5. capture DOM, accessibility tree, console, status, and network timeline;
6. restore scripts and verify recovery;
7. repeat three times on desktop and mobile.

### Sitemap transition check

1. fetch on two dates;
2. normalize URLs;
3. compare total and unique counts;
4. retain safe duplicate examples or hashes;
5. emit LiminalDB transition state.

### Private disclosure lifecycle

1. send a redacted private report;
2. request acknowledgment and a secure channel;
3. do not validate the credential;
4. record owner confirmation, rotation, or rejection as a new event;
5. recheck only public exposure after authorized remediation;
6. preserve transitions such as `STILL_PRESENT`, `REMOVED`, `CLAIM_REJECTED`, or `OWNER_CONFIRMED`.

## Submission route

- JavaScript degraded state: product/resilience feedback.
- Sitemap duplication: web-platform or SEO quality feedback.
- Accessibility candidate: accessibility channel only after criterion-mapped evidence.
- Credential signal: private security disclosure; never a public issue with exact routes before remediation.
- No bounty claim without authorized and demonstrated confidentiality, integrity, authorization, or cross-account impact.

## Authority boundary

```text
ownership = false
approval = false
execution = false
delivery = false
deployment = false
merge = false
durable_memory = false
write_mode = artifact_only
```
