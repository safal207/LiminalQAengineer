# Claude public web benchmark v0.1

## Purpose

This benchmark applies the existing LiminalQA Lighthouse decision-packet contract to seven official public Claude surfaces. It is designed to produce exact-run performance, accessibility, browser-best-practice, and SEO evidence without interacting with Claude models or authenticated user state.

## Exact inventory

1. `https://claude.ai/`
2. `https://claude.com/product/overview`
3. `https://claude.com/product/claude-code`
4. `https://platform.claude.com/docs/en/home`
5. `https://platform.claude.com/docs/en/api/overview`
6. `https://support.claude.com/en/`
7. `https://status.claude.com/`

The inventory uses current canonical destinations verified on 2026-07-19. Legacy Anthropic routes that redirect to Claude domains are not benchmarked as separate products.

## Evidence boundary

- one passive Lighthouse navigation per exact target;
- no authentication or private workspace access;
- no prompts, conversations, API calls, model calls, tools, connectors, or agents;
- no account, subscription, billing, or file operations;
- no crawling, fuzzing, load testing, bypass attempts, exploitation, or vulnerability claims;
- at most two targets execute concurrently;
- every portfolio result must contain exactly one decision packet for every reviewed URL.

## Interpretation contract

A threshold warning is a bounded quality signal, not proof of one shared root cause. Marketing pages, the unauthenticated Claude shell, documentation, support, and status surfaces may use different runtimes and must remain causally separate until evidence supports a connection.

Redirects, transient status incidents, blocked resources, consent states, and bot-protection behavior must be recorded as delivered evidence rather than silently normalized away.

## Result state

No product conclusion is recorded in this document before the first complete exact-head workflow run and artifact digest are available.
