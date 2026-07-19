# Claude public web performance report — vendor submission packet

## Purpose

This document is a concise, vendor-facing summary of passive public-page quality findings collected against official Claude web surfaces. It is intended for Anthropic Product Support or the public web performance/accessibility team.

This is not a security report and does not claim field-user impact. It is bounded laboratory evidence from repeatable Lighthouse runs with exact GitHub Actions provenance, raw reports, SHA-256 digests, Lotus verdicts, and a replayable LiminalDB-compatible ledger.

## Primary report

Pull request:

- https://github.com/safal207/LiminalQAengineer/pull/68

The PR contains the exact Claude Code rerun, Lotus supersession record, and links to the earlier seven-surface Claude benchmark and combined evidence ledger.

## Key confirmed findings

### Claude Code product page

Target:

- `https://claude.com/product/claude-code`

Exact three-run DevTools-throttled mobile experiment:

- valid LCP measurements: `3/3`
- `NO_LCP`: `0/3`
- runtime errors: `0/3`
- median Performance: `35`
- median LCP: `7.299 s`
- median TBT: `2.294 s`
- LCP range: `6.463–7.588 s`

Experiment provenance:

- workflow run: `29666017830`
- exact experiment head: `fab4cd94d237628b57abac6e74049c1c13c57756`
- result SHA-256: `79e1089146aa66a2beef0e8daf069191424ff211498877db9bc0e9f9cc1dcaf9`
- GitHub artifact SHA-256: `f281d9d0787d0e5d9565d9f42d7677a586f739a8f89cd1ae556d9a1f954d1682`

The prior single simulated-throttling report emitted `NO_LCP`, so its displayed Performance `0` was not treated as a valid product-performance score. It remains preserved as historical measurement conflict. The new repeated DevTools result supersedes the current measurement state without deleting the earlier evidence.

### Other Claude public surfaces

The earlier bounded public-web benchmark also recorded:

- Claude login shell: LCP `33.92 s`, TBT `3.99 s`, estimated unused JavaScript `2,936 KiB`;
- Claude product overview: LCP `41.43 s`, Accessibility `73`, render-blocking opportunity `2.43 s`;
- shared client-runtime contributor pattern: unused JavaScript in `6/7` packets; boot-time and bfcache findings in `5/7`;
- Claude Status: Accessibility `83`, Best Practices `79`, including bounded contrast and semantic findings.

Benchmark provenance:

- benchmark PR: `https://github.com/safal207/LiminalQAengineer/pull/62`
- evidence head: `df79bc0f6330b6430fcb3c29962c293697158037`
- workflow run: `29665084768`
- portfolio artifact SHA-256: `bc084810a9a1a5ef48cfe4d3eb6186dcc176e728761f376165cd2b07eda8a117`

## Lotus and replay evidence

The combined Lotus packet preserves confirmed findings, rejected claims, unresolved measurement conflicts, and supersession history.

Final combined state:

- findings: `13`
- confirmed: `10`
- blocked: `1`
- needs evidence: `2`
- LiminalDB-compatible events: `65`

Final integration provenance:

- workflow run: `29666257832`
- exact integration head: `e2bd8d2d3acd630b9a9757417db24ed838b76528`
- packet SHA-256: `ccea168e6ffd7e62054b97378d957b97a55bad4b5489860bf3ac47b4beb9f766`
- ledger head: `80a88fae1fdb4903450e1fe14821e410bb5e5487438fd5c36c29e7320627e7fa`
- snapshot SHA-256: `8336dbaaefc9b291b6d02fd8f98487d073d73cc1d54bd1fe08a8c24a853737bf`
- artifact SHA-256: `150cefcde13d4227edb5b28f592578a7f1a826536733f838b6d3d57b9005ff64`

## Recommended routing

Please route this report to the team responsible for Claude public web performance and accessibility. The report concerns public marketing, login, documentation, help, status, and Claude Code product pages. It does not concern model behavior, account security, API security, or authenticated product workflows.

## Suggested support message

> Hello Anthropic Product Support — I completed a passive, reproducible quality audit of official Claude public web surfaces.
>
> The strongest exact result is a three-run mobile DevTools-throttled test of the Claude Code product page: 3/3 valid LCP measurements, median LCP 7.299 s, median TBT 2.294 s, and median Performance 35. The earlier Lighthouse `NO_LCP` result was preserved as an invalid measurement state rather than reported as a product score of zero.
>
> The broader bounded benchmark also identified severe lab LCP delays on the Claude login shell and product overview, recurring unused JavaScript across 6/7 surfaces, and accessibility/best-practice findings on Claude Status.
>
> All claims are separated into confirmed, blocked, and needs-evidence states, with exact workflow runs, raw reports, SHA-256 hashes, and a replayable evidence ledger.
>
> Full report: https://github.com/safal207/LiminalQAengineer/pull/68
>
> Could you please route this to the public web performance/accessibility team? I can provide the exact artifacts if needed.

## Safety and interpretation boundary

- public pages only;
- passive navigation only;
- no authentication;
- no prompts or model calls;
- no API calls;
- no uploads;
- no fuzzing, exploitation, or load testing;
- laboratory evidence, not field telemetry;
- no ownership, approval, execution, deployment, or merge authority.
