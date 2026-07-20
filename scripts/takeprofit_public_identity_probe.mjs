#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument near ${key ?? "<end>"}`);
    }
    args[key.slice(2)] = value;
  }
  return args;
}

function countAccessibilityMatches(node, sentinel) {
  if (!node) return 0;
  const own = String(node.name || "").toUpperCase().includes(sentinel.toUpperCase()) ? 1 : 0;
  return own + (node.children || []).reduce((sum, child) => sum + countAccessibilityMatches(child, sentinel), 0);
}

async function dismissCookieBanner(page) {
  return page.evaluate(() => {
    const labels = ["accept", "accept all", "allow all", "принять", "согласен"];
    const candidate = [...document.querySelectorAll("button")].find((button) =>
      labels.includes((button.textContent || "").trim().toLowerCase()),
    );
    if (!candidate) return false;
    candidate.click();
    return true;
  });
}

async function navigate(page, url, timeoutMs, settleMs) {
  let response = null;
  let error = null;
  try {
    response = await page.goto(url, {waitUntil: "networkidle2", timeout: timeoutMs});
  } catch (caught) {
    error = String(caught?.message || caught);
  }
  await dismissCookieBanner(page).catch(() => false);
  await sleep(settleMs);
  return {
    requested_url: url,
    final_url: page.url(),
    status: response?.status() ?? null,
    navigation_error: error,
  };
}

async function inspectHome(page, config, outputDir, profileId) {
  const navigation = await navigate(
    page,
    config.targets.home,
    config.navigation_timeout_ms,
    config.settle_ms,
  );

  const dom = await page.evaluate((sentinel) => {
    const bodyText = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const upperSentinel = sentinel.toUpperCase();
    const allAnchors = [...document.querySelectorAll("a")];
    const matches = allAnchors
      .map((anchor) => {
        const rect = anchor.getBoundingClientRect();
        const style = getComputedStyle(anchor);
        const text = (anchor.textContent || "").replace(/\s+/g, " ").trim();
        const href = anchor.href || "";
        const visible =
          rect.width > 0 &&
          rect.height > 0 &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          Number(style.opacity || 1) > 0;
        const container = anchor.closest("article, li, section, div");
        const context = (container?.innerText || text).replace(/\s+/g, " ").trim().slice(0, 500);
        return {
          text,
          href,
          aria_label: anchor.getAttribute("aria-label"),
          visible,
          rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
          context,
        };
      })
      .filter((entry) =>
        entry.text.toUpperCase().includes(upperSentinel) || entry.href.toUpperCase().includes(upperSentinel),
      );

    const textOccurrences = bodyText.toUpperCase().split(upperSentinel).length - 1;
    const footerLinks = allAnchors
      .map((anchor) => {
        const text = (anchor.textContent || "").replace(/\s+/g, " ").trim();
        const rect = anchor.getBoundingClientRect();
        const style = getComputedStyle(anchor);
        return {
          text,
          href: anchor.href || "",
          visible:
            rect.width > 0 &&
            rect.height > 0 &&
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            Number(style.opacity || 1) > 0,
        };
      })
      .filter((entry) => ["Terms of Use", "Privacy Policy"].includes(entry.text));

    return {
      title: document.title,
      body_text_sha256_input: bodyText,
      sentinel_text_occurrences: textOccurrences,
      sentinel_anchor_matches: matches,
      unique_sentinel_hrefs: [...new Set(matches.map((entry) => entry.href).filter(Boolean))],
      footer_links: footerLinks,
      footer_link_counts: Object.fromEntries(
        ["Terms of Use", "Privacy Policy"].map((label) => [
          label,
          footerLinks.filter((entry) => entry.text === label).length,
        ]),
      ),
    };
  }, config.sentinel);

  const bodyText = dom.body_text_sha256_input;
  delete dom.body_text_sha256_input;
  dom.body_text_sha256 = sha256(bodyText);

  const accessibility = await page.accessibility.snapshot({interestingOnly: false}).catch(() => null);
  dom.accessibility_sentinel_matches = countAccessibilityMatches(accessibility, config.sentinel);

  await page.screenshot({
    path: path.join(outputDir, `${profileId}-home.png`),
    fullPage: true,
  });

  return {navigation, ...dom};
}

async function inspectProfile(page, config, outputDir, profileId, url, label) {
  const navigation = await navigate(page, url, config.navigation_timeout_ms, config.settle_ms);
  const state = await page.evaluate((sentinel) => {
    const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const tabs = [...document.querySelectorAll("button, a, [role='tab']")]
      .map((element) => (element.textContent || "").replace(/\s+/g, " ").trim())
      .filter(Boolean)
      .filter((value, index, values) => values.indexOf(value) === index)
      .slice(0, 100);
    return {
      title: document.title,
      body_text_sample: text.slice(0, 2500),
      body_text_sha256_input: text,
      sentinel_occurrences: text.toUpperCase().split(sentinel.toUpperCase()).length - 1,
      has_not_found_text: /not found|page does not exist|404|не найден/i.test(text),
      visible_tabs: tabs,
      drafts_visible: tabs.some((value) => /^drafts?$/i.test(value)),
    };
  }, config.sentinel);
  const bodyText = state.body_text_sha256_input;
  delete state.body_text_sha256_input;
  state.body_text_sha256 = sha256(bodyText);

  await page.screenshot({
    path: path.join(outputDir, `${profileId}-${label}.png`),
    fullPage: true,
  });
  return {navigation, ...state};
}

async function inspectDocumentation(page, config, outputDir) {
  const docsNavigation = await navigate(
    page,
    config.targets.profile_docs,
    config.navigation_timeout_ms,
    config.settle_ms,
  );
  const docs = await page.evaluate(() => {
    const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const lower = text.toLowerCase();
    const publicIndex = lower.indexOf("public profile");
    const draftsIndex = lower.indexOf("draft");
    const contextAround = (index) =>
      index < 0 ? null : text.slice(Math.max(0, index - 220), Math.min(text.length, index + 500));
    return {
      title: document.title,
      mentions_public_profile: publicIndex >= 0,
      mentions_drafts: draftsIndex >= 0,
      public_profile_context: contextAround(publicIndex),
      drafts_context: contextAround(draftsIndex),
      body_text_sha256_input: text,
    };
  });
  const docsText = docs.body_text_sha256_input;
  delete docs.body_text_sha256_input;
  docs.body_text_sha256 = sha256(docsText);
  await page.screenshot({path: path.join(outputDir, "docs-user-profile.png"), fullPage: true});

  const reference = await inspectProfile(
    page,
    config,
    outputDir,
    "desktop",
    config.targets.reference_profile,
    "reference-profile",
  );

  return {
    docs_navigation: docsNavigation,
    docs,
    reference_profile: reference,
    ambiguity_candidate:
      docs.mentions_public_profile && docs.mentions_drafts && reference.drafts_visible === false,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = args.config;
  const chromePath = args.chrome;
  const outputDir = args["output-dir"];
  if (!configPath || !chromePath || !outputDir) {
    throw new Error("Required: --config --chrome --output-dir");
  }

  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  await fs.rm(outputDir, {recursive: true, force: true});
  await fs.mkdir(outputDir, {recursive: true});

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });

  const profileResults = [];
  try {
    for (const profile of config.profiles) {
      const page = await browser.newPage();
      page.setDefaultNavigationTimeout(config.navigation_timeout_ms);
      await page.setUserAgent(profile.user_agent);
      await page.setViewport(profile.viewport);

      const home = await inspectHome(page, config, outputDir, profile.id);
      const sentinelHref = home.unique_sentinel_hrefs[0] || config.targets.sentinel_profile;
      const sentinelProfile = await inspectProfile(
        page,
        config,
        outputDir,
        profile.id,
        sentinelHref,
        "sentinel-profile",
      );
      profileResults.push({
        profile: profile.id,
        user_agent: profile.user_agent,
        viewport: profile.viewport,
        home,
        sentinel_profile: sentinelProfile,
      });
      await page.close();
    }

    const docsPage = await browser.newPage();
    const desktop = config.profiles.find((profile) => profile.id === "desktop") || config.profiles[0];
    await docsPage.setUserAgent(desktop.user_agent);
    await docsPage.setViewport(desktop.viewport);
    const documentation = await inspectDocumentation(docsPage, config, outputDir);
    await docsPage.close();

    const identityConfirmed = profileResults.every(
      (entry) =>
        entry.home.sentinel_text_occurrences > 0 &&
        entry.home.sentinel_anchor_matches.some((anchor) => anchor.visible) &&
        entry.home.accessibility_sentinel_matches > 0,
    );
    const profileRouteBroken = profileResults.every(
      (entry) =>
        (entry.sentinel_profile.navigation.status !== null && entry.sentinel_profile.navigation.status >= 400) ||
        entry.sentinel_profile.has_not_found_text,
    );
    const duplicateFooterCandidate = profileResults.some(
      (entry) =>
        entry.home.footer_link_counts["Terms of Use"] > 1 ||
        entry.home.footer_link_counts["Privacy Policy"] > 1,
    );

    const result = {
      schema_version: "liminalqa-takeprofit-public-identity-result-v1",
      observed_at: new Date().toISOString(),
      center_of_coordinates: {
        O: "public URL + profile + viewport + language + navigation time + unauthenticated state",
        observer: "passive unauthenticated browser",
        axes: {
          X: "domain -> route -> feed card -> author anchor -> profile route",
          Y: "rendered -> accessible -> navigable -> not-found/valid-profile",
          Z: "desktop/mobile user-agent and viewport",
          T: "initial navigation -> settled feed -> author navigation -> profile state",
        },
      },
      config_sha256: sha256(JSON.stringify(config)),
      profiles: profileResults,
      documentation,
      verdicts: {
        public_identity_sentinel: identityConfirmed ? "CONFIRMED_PUBLIC_SURFACE" : "NOT_CONFIRMED",
        sentinel_profile_route: profileRouteBroken ? "CONFIRMED_BROKEN_ROUTE" : "ROUTE_REQUIRES_REVIEW",
        public_profile_drafts_documentation: documentation.ambiguity_candidate
          ? "CONFIRMED_DOCUMENTATION_AMBIGUITY"
          : "NOT_CONFIRMED",
        duplicate_footer_semantics: duplicateFooterCandidate ? "NEEDS_ACCESSIBILITY_REVIEW" : "NOT_OBSERVED",
      },
      authority: {
        mode: "evidence_only",
        grants: {
          ownership: false,
          approval: false,
          execution: false,
          delivery: false,
          deployment: false,
          external_submission: false,
          merge: false,
        },
      },
      boundaries: config.boundaries,
      limitations: config.limitations,
    };

    const resultPath = path.join(outputDir, "takeprofit-public-identity-result.json");
    const resultText = `${JSON.stringify(result, null, 2)}\n`;
    await fs.writeFile(resultPath, resultText);

    const rows = profileResults
      .map(
        (entry) =>
          `| ${entry.profile} | ${entry.home.sentinel_text_occurrences} | ${entry.home.sentinel_anchor_matches.filter((anchor) => anchor.visible).length} | ${entry.home.accessibility_sentinel_matches} | ${entry.sentinel_profile.navigation.status ?? "n/a"} | ${entry.sentinel_profile.has_not_found_text ? "yes" : "no"} |`,
      )
      .join("\n");

    const summary = `# TakeProfit public identity sentinel audit\n\n` +
      `Observed: ${result.observed_at}\n\n` +
      `## Verdicts\n\n` +
      `- Public identity sentinel: **${result.verdicts.public_identity_sentinel}**\n` +
      `- Sentinel profile route: **${result.verdicts.sentinel_profile_route}**\n` +
      `- Public-profile drafts documentation: **${result.verdicts.public_profile_drafts_documentation}**\n` +
      `- Duplicate footer semantics: **${result.verdicts.duplicate_footer_semantics}**\n\n` +
      `## Coordinate center\n\n` +
      `O = public URL + browser profile + viewport + unauthenticated state + observation time.\n\n` +
      `Observer N = passive browser; no login, forms, direct API calls, financial actions, fuzzing, or server-state change.\n\n` +
      `## Profile matrix\n\n` +
      `| Profile | Sentinel text | Visible author links | Accessibility matches | Profile HTTP | Not-found text |\n` +
      `|---|---:|---:|---:|---:|---|\n${rows}\n\n` +
      `## Bounded causal trajectory\n\n` +
      `unfinished or missing username state -> literal sentinel reaches public feed -> sentinel becomes an accessible author link -> navigation targets a placeholder profile route -> authorship trust and recovery are reduced.\n\n` +
      `## Documentation trajectory\n\n` +
      `public-profile documentation mentions Drafts -> unauthenticated reference profile does not expose a Drafts tab -> owner-only/public visibility boundary is ambiguous in the guide.\n\n` +
      `## Evidence files\n\n` +
      `- takeprofit-public-identity-result.json\n` +
      `- desktop-home.png / mobile-home.png\n` +
      `- desktop-sentinel-profile.png / mobile-sentinel-profile.png\n` +
      `- docs-user-profile.png / desktop-reference-profile.png\n`;
    await fs.writeFile(path.join(outputDir, "takeprofit-public-identity-summary.md"), summary);
    await fs.writeFile(
      path.join(outputDir, "SHA256SUMS.txt"),
      `${sha256(resultText)}  takeprofit-public-identity-result.json\n${sha256(summary)}  takeprofit-public-identity-summary.md\n`,
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
