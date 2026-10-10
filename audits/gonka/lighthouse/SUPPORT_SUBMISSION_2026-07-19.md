# Gonka support submission

**Status:** SENT  
**Date:** 2026-07-19  
**Recipient:** `hello@productscience.ai`  
**Subject:** `Gonka web and documentation accessibility report — Lighthouse evidence`

## Delivery

The product/accessibility report was sent by email from the connected Gmail account.

Gmail message id: `19f7a24691f63bc8`

The first attempt with the Decision Packet and full ZIP attached was rejected by the mail proxy. A second attempt was sent successfully without attachments and included direct evidence references:

- Draft PR: `https://github.com/safal207/LiminalQAengineer/pull/83`
- GitHub Actions run: `29684917873`
- Audit evidence head: `bc24e50c8d0690077e5a588ba26755095b1ee266`
- Protocol head: `8a35022bea25ebee4b7356314a0a262edbaa82db`
- Documentation head: `902f9074b70cbdbcbf9343bc0e22a153503b87aa`

## Submitted findings

1. HackerOne report iframe lacks an accessible title.
2. Documentation search dialog lacks an accessible name.
3. Developer and Host Quickstarts contain repeated contrast and color-only-link failures.
4. Home and documentation landing pages lack a valid document title.
5. Relative hreflang URLs are rejected on every tested route.
6. Page-relative sitemap requests return 404.
7. Landing page emits repeatable JavaScript exceptions.
8. Landing-page navigation includes unnamed links and insufficient touch targets.

## Boundaries communicated

- passive public GET navigation only;
- no wallet connection or signature;
- no transactions, inference, node/mining operations, enumeration, fuzzing, port scanning, or load testing;
- no confirmed security vulnerability;
- no HackerOne submission;
- performance values remain preliminary until the three-run evidence pass.
