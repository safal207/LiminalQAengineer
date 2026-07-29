---
name: logo-fidelity-transfer
description: Compare a reference logo with source SVG assets and the rendered website, then guide an evidence-bound transfer into an authorized web repository. Use for brand-logo audits, pixel-accurate logo migration, SVG geometry review, responsive lockups, or visual-regression acceptance.
---

# Logo Fidelity Transfer

## Purpose

Protect the first and most recognizable brand surface: the logo. This skill compares the approved reference, the canonical vector source, and the browser-rendered result before any transfer is called complete.

The workflow is evidence-first. A visually plausible approximation is not accepted when the approved artwork can be measured. The skill has advisory and evidence authority only; it cannot claim trademark rights, approve a redesign, deploy, merge, or publish a brand change without explicit human authorization.

## Open-source foundation

Use these components by default:

- `microsoft/playwright` as the browser and selector-capture backbone. It provides deterministic locator screenshots, desktop/mobile profiles, multiple browser engines, tracing, and CI-friendly execution.
- `mapbox/pixelmatch` as the pixel-level comparison engine. It produces mismatch counts and diff images while accounting for anti-aliasing.
- native XML/SVG parsing for structural checks. Add an SVG manipulation library only when actual path editing is authorized and necessary.

Do not use OCR output as logo geometry. OCR can help locate a wordmark in a reference image, but it cannot define the shapes, kerning, cap-height, baseline, or trademarked glyph contours.

## Required inputs

Resolve or mark missing:

- approved reference file or clearly identified crop;
- reference provenance and permission to use the identity;
- target repository and exact commit SHA;
- target page URL or local route;
- stable logo selector or asset path;
- expected lockups: primary, compact, header, mobile, mark, favicon;
- viewports and device-pixel ratios;
- canonical colors, clear-space rules, and any known geometry grid;
- allowed write, deployment, and merge authority;
- stop conditions.

If the reference is missing, ambiguous, low-resolution, perspective-distorted, or cropped through the mark, return `NEEDS_EVIDENCE`. Do not reconstruct a supposedly exact logo from memory.

## Evidence ladder

```text
reference image only
-> REFERENCE_SIGNAL

reference + canonical asset provenance
-> SOURCE_BOUND

normalized reference + selector screenshot
-> COMPARABLE

pixel diff + SVG geometry + cross-viewport reproduction
-> FIDELITY_CANDIDATE

human brand-owner review
-> APPROVED_FOR_TRANSFER | REJECTED | NEEDS_EVIDENCE
```

No automated score grants brand approval.

## Workflow

### 1. Freeze the source of truth

Hash the supplied reference and record:

- file name and SHA-256;
- dimensions, color mode, alpha state, and background;
- crop rectangle and any perspective correction;
- whether it is primary artwork, a photo of merchandise, a screenshot, or a derivative mockup;
- the human or document that designates it as approved.

A cup photo can establish recognizable letterform evidence, but perspective, printing, lighting, and lens distortion must remain explicit limitations.

### 2. Inventory the implementation

Locate every production identity surface:

- SVG/PNG/WebP assets;
- inline SVG and `<symbol>/<use>` definitions;
- CSS backgrounds and masks;
- HTML preload and cache-busting references;
- PWA manifest, favicon, maskable icon, and Apple touch icon;
- Service Worker precache and exact-revision routing;
- fallback text or legacy badge markup.

Record one canonical master for each approved lockup. Duplicate raw `d=` geometry across files is a drift risk; prefer shared definitions or generated assets with a verified identity contract.

### 3. Validate SVG structure

For each master SVG, inspect:

- `viewBox`, intrinsic dimensions, and safe margins;
- accessible `<title>` and `<desc>`;
- absence of font-dependent `<text>` when exact glyph fidelity is required;
- canonical fills/strokes and color values;
- path identity across lockups;
- cap-height, baseline, overshoot, stroke weight, and kerning constraints;
- preservation of custom marks and apostrophes;
- absence of CSS stretching such as uncontrolled `scaleX`;
- reuse through `<defs>`, `<symbol>`, or a deterministic generator where appropriate.

Geometry rules must be stated numerically when evidence supports them. Example: `R/Y cap-height y=18, baseline y=132`; a curve crossing those bounds is a measurable mismatch, not merely a stylistic opinion.

### 4. Normalize the comparison

Reference and actual images must be made comparable without hiding differences:

1. isolate the same lockup and content bounds;
2. preserve aspect ratio;
3. render on the same explicit background;
4. convert to the same color space and alpha treatment;
5. align using transparent bounds or declared anchors;
6. scale once with a recorded algorithm;
7. keep both the original and normalized files.

Never force two different aspect ratios into the same rectangle. A dimension mismatch that cannot be explained by clear space remains `BLOCKED`.

### 5. Capture the rendered logo with Playwright

Use stable locators rather than coordinate crops. For every required profile:

- navigate to the exact route;
- wait for fonts, images, styles, and the declared settled state;
- assert the locator is visible and unique;
- record its bounding box and computed style;
- capture `locator.screenshot()` with animations disabled;
- capture one surrounding-context screenshot;
- record browser engine, viewport, DPR, locale, color scheme, source SHA, and timestamp;
- repeat after hard reload or cache reset when stale delivery is a risk.

Minimum profiles are desktop and mobile. Add Chromium, WebKit, and Firefox when browser rendering is load-bearing.

### 6. Compare with Pixelmatch

Produce for every profile:

- normalized expected image;
- actual selector screenshot;
- binary or highlighted diff;
- overlay/slider-ready pair;
- mismatched-pixel count and ratio;
- mismatch bounding box;
- threshold and anti-alias settings;
- human-readable contact sheet.

Use a strict threshold for flat vector marks, then adjudicate anti-aliased edge noise separately from structural mismatch. A low global mismatch ratio does not excuse a recognizable wrong glyph, missing apostrophe, altered organic mark, or baseline break.

### 7. Adjudicate by region and invariant

Separate findings into:

- `GLYPH_SHAPE` — wrong contour or internal counter;
- `VERTICAL_METRICS` — cap-height, baseline, overshoot;
- `KERNING` — wrong spacing rhythm;
- `COLOR` — canonical color mismatch;
- `ASPECT_RATIO` — stretching or compression;
- `CLEAR_SPACE` — insufficient or inconsistent margin;
- `DELIVERY` — stale cache, wrong asset, preload, fallback flash;
- `RESPONSIVE_LOCKUP` — wrong variant for available space;
- `ACCESSIBILITY` — missing accessible name or misleading fallback;
- `REFERENCE_LIMITATION` — evidence cannot support an exact claim.

Prioritize recognizable structural errors over diffuse raster noise.

### 8. Transfer into the authorized site

Only after the canonical asset is accepted:

1. update the smallest set of source masters;
2. propagate through deterministic reuse or generation;
3. update CSS/HTML references and cache revision;
4. update PWA/manifest/icon surfaces when affected;
5. remove obsolete fallback marks without removing accessible text;
6. regenerate integrity evidence;
7. run the same Playwright + Pixelmatch matrix against the proposed branch;
8. preserve before/after/diff artifacts;
9. require human visual sign-off before merge or deployment.

Do not replace a logo with a newly generated approximation when an approved vector can be extracted or supplied.

## Acceptance contract

A transfer can be recommended only when:

- reference provenance is recorded;
- exact source identity is frozen before and after evidence collection;
- all required lockups are present;
- custom glyphs and mark paths satisfy declared geometry invariants;
- aspect ratio is preserved;
- desktop and mobile selector captures use the intended asset;
- no legacy mark flashes under delayed CSS or stale cache;
- mismatch regions are explained and accepted, not merely below one aggregate percentage;
- accessibility text remains correct;
- integrity and security checks pass;
- an authorized human approves the visual result.

## Fail-closed states

- `NOT_RUN` — no current browser or geometry evidence exists.
- `NEEDS_EVIDENCE` — reference, provenance, crop, selector, or environment is insufficient.
- `INCOMPARABLE` — normalization would distort one side or compare different lockups.
- `BLOCKED` — authority, exact source identity, or required runtime is unavailable.
- `FIDELITY_FAIL` — a required glyph, mark, color, metric, or delivery invariant differs.
- `READY_FOR_HUMAN_REVIEW` — automated evidence is complete, but approval is still human.

Missing evidence is never success. Pixel similarity is never trademark or design approval.

## Output

Return:

1. scope, reference provenance, and authority;
2. selected open-source stack and pinned versions;
3. asset and delivery inventory;
4. reference normalization record;
5. SVG geometry table;
6. viewport/browser capture matrix;
7. expected/actual/diff artifact index;
8. findings by invariant and region;
9. limitations and competing explanations;
10. transfer plan or bounded patch;
11. acceptance verdict and required human decision;
12. smallest next action and stop condition.
