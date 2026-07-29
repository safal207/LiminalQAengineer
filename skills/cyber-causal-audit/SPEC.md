# Cyber Causal Audit — Maintenance Contract

## Intent

Maintain a portable, evidence-first cybersecurity workflow that combines repository-grounded threat modeling, causal adjudication, lifecycle invariants, static and differential review, bounded experiments, false-positive verification, exact-head evidence, and explicit authority limits.

## Scope

The skill covers:

- repositories, pull requests, CI and release workflows;
- authentication, authorization, session and secret boundaries;
- stateful and distributed lifecycle review;
- supply chain, dependencies, artifacts and agent skills;
- bounded runtime discriminators in authorized environments;
- advisory security findings and next-action selection.

The skill does not authorize exploitation, credential use, production stress, external disclosure, remediation, deployment, delivery, or merge.

## Trigger context

Trigger when a user explicitly requests cybersecurity review, AppSec, threat modeling, secret or authorization review, race or resource-leak analysis, agent-skill security review, or a causal investigation of a security-relevant symptom.

Do not trigger merely because code contains words such as `token`, `redis`, `password`, or `security`.

## Source and evidence model

External methods are recorded in `sources.json` with:

- canonical repository;
- exact commit SHA;
- selected paths and concepts;
- license status;
- adoption mode.

The default adoption mode is `INSPIRED_NOT_VENDORED`. Third-party scripts, prompts, hooks, plugins and rules are not executed by default.

Every repository finding must bind:

- exact commit;
- exact path or state transition;
- violated invariant;
- competing explanation;
- bounded next discriminator;
- claim level, severity and confidence;
- authority boundary.

## Reference architecture

```text
causal-deep-audit
  -> cyber-causal-audit
      -> websocket-redis-lifecycle when applicable
      -> evidence-capture
      -> causal-adjudication
      -> exact-head-governance
      -> replay-memory
      -> product-impact
      -> transition-next-action
```

## Evaluation expectations

A valid evaluation set includes positive and negative cases for:

1. exact source pinning and license presence;
2. rejection of mutable remote execution;
3. untrusted-skill prompt and script review;
4. mock versus live evidence separation;
5. vulnerability candidate versus confirmed vulnerability language;
6. root-cause hypothesis versus confirmed root cause;
7. severity versus confidence separation;
8. secret redaction;
9. authorization and mutating-operation gates;
10. lifecycle identity and add/remove symmetry;
11. multi-socket and reconnect-generation cleanup;
12. self-echo and duplicate delivery;
13. production-safe stop conditions;
14. human disclosure and merge authority.

A prose rule without a negative test is advisory and must not be represented as an enforced contract.

## Known limitations

- Static review cannot prove deployment reachability.
- Public clients cannot confirm server-side resource cleanup.
- Analog repositories can suggest discriminating tests but cannot establish another product's architecture.
- Model diversity can reduce correlated review errors but does not replace deterministic evidence.
- Vendor ownership of a skill repository does not establish that every contribution or script is safe.
- Security severity may require owner context about deployment, tenancy, data sensitivity, scale and existing controls.

## Maintenance rules

- Revalidate external source pins before materially changing the skill.
- Review license changes before copying or vendoring any content.
- Keep `SKILL.md` below 500 lines when practical; move durable inventories and evaluation details into companion files.
- Preserve rejected hypotheses and false positives in the evidence ledger.
- Add a regression test for every new semantic guard.
- Do not widen tool permissions silently.
- Keep runtime network and write authority disabled unless a separate reviewed contract explicitly enables them.
- Require human review for severity, disclosure, remediation ownership and merge.
