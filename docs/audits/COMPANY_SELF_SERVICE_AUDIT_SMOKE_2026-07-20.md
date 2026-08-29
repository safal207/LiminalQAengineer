# Company self-service audit smoke — 2026-07-20

## Verdict

The reusable LiminalQA company audit pipeline completed an end-to-end public smoke test successfully.

```text
company-owned contract
→ fail-closed validation
→ exact caller and engine revisions
→ desktop/mobile matrix
→ passive browser and keyboard observation
→ pinned Lighthouse evidence
→ exact-attempt manifests
→ 2/2 manifest aggregation
→ reusable outputs and evidence artifact
```

Workflow execution status: **PASS**.

The audited example portfolio returned an aggregate quality verdict of `WARN / LOW` because `example.com` scored `80` for SEO against the example threshold of `85`. This is expected evidence behavior, not a workflow failure. Browser accessibility signals were all zero.

## Exact execution

```text
workflow: Company Public Audit Engine CI
run: 29766920933
attempt: 1
engine SHA: b45239e0f284d3205bdc6f3a77de5649bb6fadc5
caller repository: safal207/LiminalQAengineer
caller SHA: c33ae65b7ca4e26b07195b9e7f01d48d01119e73
config SHA-256: 3539e76d19f9a93428242e5d8ed4cb6d5bee2779b303e205420d45b6f836e26f
```

## Passed gates

- `actionlint` with pinned `v1.7.7`;
- Python, Node and JSON syntax;
- fail-closed contract unit tests;
- deterministic example contract and matrix;
- reusable-workflow contract preparation;
- desktop browser and Lighthouse cell;
- mobile browser and Lighthouse cell;
- exact run/attempt manifest enforcement;
- aggregate report and SHA-256 generation;
- aggregate artifact upload;
- evidence-only `fail_on: never` gate.

## Cell results

| Cell | HTTP | Performance | Accessibility | Best Practices | SEO | Browser accessibility signals |
|---|---:|---:|---:|---:|---:|---|
| `home-desktop` | 200 | 100 | 100 | 96 | 80 | none |
| `home-mobile` | 200 | 100 | 100 | 96 | 80 | none |

Both cells reported:

```text
keyboard_focus_gap: false
unnamed_sequential_controls: 0
nested_interactive_controls: 0
unnamed_accessibility_controls: 0
```

## Aggregate artifact

```text
artifact ID: 8471326847
artifact: liminalqa-company-audit-29766920933-1
artifact digest: sha256:0f08e1b07a8163f12ef0568651831b6cd1a2e777fdc67ad1ad5b9250e452c70c
```

Aggregate content hashes:

```text
company-audit-result.json:
905ae9bbd3c022e96a4b75bf37c5ce90a9a033db505d320a6bd0aa944e603377

company-audit-summary.md:
5725b93f8378b683715897b9a065bc8a52e9f0cea400936cd21d07e97bb5c4e2

evidence-index.md:
67ea9b2ad6f49eddc0014e6aad240ce8658e49f56a9e05f4471fa69311158950

workflow-outputs.json:
af06931e0fdbe7bad3db4f24050c7c5c34af1191a13d5f26a8cec6459662a9ae

aggregate-exact-attempt.json:
9747b837d07d949f4ede0fd112bae2bcb2e1df464d617d3cfbaf0059651db79a
```

## Per-cell evidence

### Desktop

```text
artifact ID: 8471266753
artifact digest: sha256:f907d0e662e3b000670044aef14e9ae5d736a5c5e6cd0ed008ff77232308b171
browser result: 9416e2aebbaa7a4d42a1bb1dd87cb8472493e4f60d04b64d8444383ab033d2b8
Lighthouse summary: a88ae84227e6c4723cf8827303094fdd7d07d7931d84dba1fc62708fb80f25d9
exact-attempt manifest: 00f2a8a9276f41c822083a748471bca70a983799cbb91633288bb75134f523ba
```

### Mobile

```text
artifact ID: 8471247582
artifact digest: sha256:30db3f008a15cc981bb5746f59b927d32db7617a63c81199b4dd1e57ae2255c4
browser result: 77ae022cec75748962a42dbf7ce4dd680e9dda6aee1c438aba22bacc1e6a89fd
Lighthouse summary: fe848d5b08560ea71a169ccda52ff2b634a9e415edbd666aa4c32bf9457aa64b
exact-attempt manifest: b1720a3af14fd84d6e74e02e5cad7e90856d9b155acff11224e2bff0d285bb45
```

## Contract and lint evidence

```text
validated contract artifact ID: 8471215620
validated contract digest: sha256:b9b98a1c5a0ba85b74d5bcabdbc9db3675e3fcfb4c5d4dc481e4c6e2c7df0aca

actionlint artifact ID: 8471208472
actionlint artifact digest: sha256:076e49166fe92d80b0c0260db901099b973c223895b82f07f743de1cfac6fe35
```

## How a company calls it

The company commits its bounded JSON contract and adds a small caller workflow:

```yaml
jobs:
  public-audit:
    uses: safal207/LiminalQAengineer/.github/workflows/company-public-audit.yml@PINNED_LIMINALQA_SHA
    with:
      config_path: .github/liminalqa/public-audit.json
      engine_ref: PINNED_LIMINALQA_SHA
      retention_days: 30
      fail_on: never
```

The same reviewed SHA or release tag should be used in both positions so the workflow definition and engine scripts cannot silently come from different revisions.

## Safety boundary

The successful smoke used a public HTTPS route only. The engine does not accept credentials, cookies, custom request headers, authentication, account access, JavaScript injection, form submission, direct application APIs, publishing, financial operations, fuzzing, exploitation or load testing.

The result is quality and accessibility evidence. It is not a penetration test, vulnerability report, compliance certification or automatic defect judgment.

## Authority

The pipeline produces evidence and optional quality gates only. It grants no ownership, approval, external-submission, deployment or merge authority.
