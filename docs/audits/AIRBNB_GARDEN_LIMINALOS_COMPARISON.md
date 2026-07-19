# Airbnb GardenLiminal + LiminalOSAI comparison v0.1

## Question

Does adding GardenLiminal and LiminalOSAI change the existing Lotus conclusion for the exact Airbnb currency/history evidence, and what additional evidence do the two runtimes provide?

## Candidate

The benchmark reuses the exact Antalya artifact from the Airbnb execution matrix:

```text
execution PR: #77
adjudication PR: #80
execution head: 404da0d714de334e18080138623370fdc32717f5
workflow run: 29678020284
artifact: ABNB-MATRIX-antalya-center
artifact digest: sha256:55030ae08db9d7f462aec48a75ce11873deb32d4f44255ffc01c3b7b1e06ad49
```

The source result contained two fresh browser contexts with the same visible reservation-currency sequence:

```text
TRY → EUR → TRY after Back → EUR after Forward
```

The existing Lotus decision is `NO_DEFECT_OBSERVED` for this exact listing and date window.

## Fair-comparison rule

This benchmark performs no new Airbnb navigation. It downloads the exact workflow artifact and replays it.

That isolates the effect of the evidence architecture from changes in:

- listing availability;
- date availability;
- Airbnb deployment state;
- geolocation;
- anti-automation behavior;
- browser version;
- network conditions.

A later live Garden execution should be a separate experiment, not silently mixed into this comparison.

## GardenLiminal role

GardenLiminal is pinned to:

```text
repository: safal207/GardenLiminal
commit: 6c30422d0492ec312a35624322f90a7761419655
```

The workflow:

1. builds the exact source;
2. runs its unit tests;
3. creates a minimal Alpine root filesystem;
4. validates a bounded Seed manifest;
5. attempts one `/bin/true` process inside GardenLiminal;
6. captures build, test, inspect, run, and lifecycle logs.

This checks whether the benchmark runner can support GardenLiminal. It does **not** prove that the historical Airbnb browser artifact was Garden-isolated.

The original artifact can receive Garden execution provenance only from a future run in which the browser probe itself is launched by Garden and its lifecycle events are bound to the same run ID and evidence manifest.

## LiminalOSAI role

LiminalOSAI is pinned to:

```text
repository: safal207/LiminalOSAI
commit: a2c5783287a9def4b4254b9436c2e75468613dca
```

The workflow runs:

```text
make
make check
make test
pulse_kernel --dry-run --limit=2 --trace --coherence --reflect --introspect
```

This validates the experimental runtime capability only. LiminalOSAI is not allowed to:

- confirm an Airbnb product defect;
- override exact evidence;
- convert an aborted request into user impact;
- grant execution or merge authority;
- claim production safety enforcement.

A future adapter may translate selected trace records into a separate advisory signal document. Lotus must still adjudicate those signals under explicit evidence rules.

## Deterministic replay checks

The comparator verifies:

- exact `probe-result.json` SHA-256;
- exact `manifest.json` SHA-256;
- every manifest file hash;
- exact Airbnb listing ID at all eight checkpoints;
- visible currency and requested/URL currency alignment;
- two exact `TRY → EUR → TRY → EUR` sequences;
- no runtime, console, page, or HTTP 4xx/5xx errors;
- no payment submission or reservation creation;
- aborted request counts and hosts as diagnostic signals only.

A request abort does not become a product defect without a demonstrated inconsistent state, failed product request, or user impact.

## Expected interpretation

The expected product decision remains:

```text
NO_DEFECT_OBSERVED
```

The expected evidence improvement is:

```text
old:
Docker browser evidence + Lotus judgment

new:
exact evidence replay
+ target-drift verification
+ full manifest verification
+ Garden capability and lifecycle evidence
+ LiminalOSAI capability evidence under an advisory-only boundary
+ unchanged Lotus truth boundary
```

The useful result is not “more bugs.” It is a clearer answer to three separate questions:

1. Did the product state contradict the expected transition?
2. Was the execution environment observable and bounded?
3. Is an experimental runtime signal a hypothesis or admissible evidence?

## Authority and safety

The benchmark is audit-only. It performs no authentication, form submission, host contact, payment, reservation, crawling, fuzzing, load testing, bypass, exploitation, or external submission.

Ownership, approval, execution, delivery, external-submission, deployment, and merge authority remain false.
