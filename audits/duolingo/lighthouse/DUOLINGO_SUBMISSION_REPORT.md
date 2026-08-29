# Duolingo Web Lighthouse Submission Report

Status: ready for product/accessibility submission after manual reproduction notes are attached.

## Evidence identity

- GitHub Actions run: `29683522256`
- Pull request: `#82`
- Exact evidence head: `ec1916811bed32d4c59c6449464da7a391956004`
- Valid Lighthouse reports: 10
- Profiles: mobile and desktop
- Lighthouse CI: `0.15.1`
- Lighthouse: `12.6.1`
- Chrome: `150.0.7871.114`

## Lotus verdict

```yaml
execution: PASS
raw_lhr_count: 10
performance: NEEDS_EVIDENCE
accessibility_structure: PRODUCT_SIGNAL
share_template: PRODUCT_SIGNAL
security_vulnerability: NOT_CONFIRMED
external_target_maximum: WARN
overall_decision: WARN
```

## Finding 1 — Browser zoom is disabled

Affected routes:

- `https://www.duolingo.com/`
- `https://www.duolingo.com/log-in`
- `https://www.duolingo.com/register`
- `https://www.duolingo.com/share-direct/sm`

Observed evidence:

```html
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
```

Lighthouse failed the viewport zoom audit in both mobile and desktop evidence profiles.

Expected result: users should be able to zoom the page using browser and operating-system controls.

Suggested fix: remove `user-scalable=no` and avoid restrictive maximum-scale values.

Priority: `P2`.

## Finding 2 — Invalid list semantics on registration

Affected route: `https://www.duolingo.com/register`

Observed evidence: a `ul` element contains direct `button` children rather than list items. The failure repeated in both profiles.

Expected result: list containers should contain valid list-item semantics, or the container should use a structure appropriate for a group of buttons.

Priority: `P2`.

## Finding 3 — Registration images lack alternative text

Affected route: `https://www.duolingo.com/register`

Observed evidence: 42 image nodes failed the Lighthouse `image-alt` audit in both profiles.

Expected result: meaningful images should have descriptive alternative text; decorative images should have `alt=""`.

Priority: `P2`.

## Finding 4 — Repeated text contrast failures

Contrast failures repeated across mobile and desktop. The registration route produced 40 failing nodes in mobile and 41 in desktop. Other public routes also contained failing nodes.

Expected result: text and interactive controls should meet applicable WCAG contrast requirements in each state.

Priority: `P2`, pending manual visual confirmation for representative elements.

## Finding 5 — Empty streak-sharing template and undefined user requests

Affected route: `https://www.duolingo.com/share-direct/sm`

Observed visible structure:

```text
I’m on a
[number missing]
day language learning streak!
```

The page also made unauthenticated requests containing an undefined user identifier, including paths similar to:

```text
/users/undefined/streak-goal-current
/users/undefined/streak-goal-next-options
```

Those requests returned HTTP 404 responses.

Expected result: the generic route should validate required share data before rendering. It should either display a valid streak value, redirect to a generic page, or return a non-indexable error state without issuing malformed user requests.

Priority: `P2`.

## Finding 6 — Repeated public-page 404 console/network noise

Repeated failed resource requests were recorded on the main, login, registration and streak-sharing routes.

Priority: `P3`. Individual failed resources should be grouped by root cause before separate tickets are created.

## Performance boundary

Low laboratory performance scores were observed, but this PR smoke pass collected one run per URL and several pages emitted slow/incomplete-load warnings. Performance remains `NEEDS_EVIDENCE` until the manual workflow completes three runs per URL and median/variance analysis.

## Retracted finding

The earlier hypothesis that the Turkish `/imprint` route leads to a 404 is retracted. Both real Lighthouse reports followed the redirect to `about.duolingo.com`, received HTTP 200 and captured visible Impressum content.

## Submission routing

### Product and accessibility findings

Submit through the official Duolingo Help Center:

`https://www.duolingo.com/help`

Recommended subject:

`Duolingo Web accessibility and empty streak-sharing issues — Lighthouse evidence attached`

Attach the concise Decision Packet first. Offer raw mobile/desktop evidence archives if the support team requests them.

### security.txt standards issue

Send separately to:

`security@duolingo.com`

Do not mix the accessibility and product findings into the security email. The security message should be limited to RFC 9116 interoperability and disclosure-process observations and should explicitly state that no intrusive testing was performed.

## Attachments

Recommended initial attachment:

- `duolingo_lighthouse_decision_packet_run_29683522256.md`

Available technical evidence:

- `duolingo_lighthouse_decision_packet_run_29683522256.json`
- mobile Lighthouse evidence archive
- desktop Lighthouse evidence archive
- combined evidence bundle

## Final boundary

This report does not claim compromise, unauthorized access, a bounty-eligible vulnerability or complete WCAG conformance testing. It documents reproducible automated product/accessibility signals and one corrected false positive.
