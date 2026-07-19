# Gonka public audit preflight

**Date:** 2026-07-19  
**Mode:** passive public GET/HEAD only  
**Pythia:** `ALLOW_WITH_CONSTRAINTS`

## Target

- Public website and documentation: `https://gonka.ai`
- Protocol repository: `gonka-ai/gonka` at `8a35022bea25ebee4b7356314a0a262edbaa82db`
- Documentation repository: `gonka-ai/gonka-docs` at `902f9074b70cbdbcbf9343bc0e22a153503b87aa`

## Official reporting boundary

Gonka documents an official HackerOne program and instructs researchers to submit security vulnerabilities through its private form rather than public issues, pull requests, or chats.

This adapter does not submit to HackerOne. It only produces evidence. A report can be promoted to a security candidate only after scope, impact, likelihood, and prohibited-action checks pass.

## Prohibited actions

- wallet connection or signature;
- account or key creation;
- token transfers, bridge operations, governance actions or transactions;
- inference requests or API-key generation;
- node, host, mining, MLNode or gateway operation;
- port scanning, account enumeration, fuzzing, load testing or denial-of-service simulation;
- disclosure of a potential vulnerability in the public audit PR.

## Public audit routes

1. Home
2. Documentation landing page
3. Developer quickstart
4. Host quickstart
5. Vulnerability reporting page

## Decision policy

- Lighthouse score only → `NEEDS_EVIDENCE`
- repeated mobile/desktop structural failure → `PRODUCT_SIGNAL`
- repeated three-run failure plus manual impact → `CONFIRMED_PRODUCT_DEFECT`
- demonstrated CIA/network impact inside HackerOne scope → private `SECURITY_CANDIDATE`
- external target final automation verdict → maximum `WARN`
