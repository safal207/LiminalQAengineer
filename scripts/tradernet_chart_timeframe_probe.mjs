#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer-core";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`Invalid argument near ${key}`);
    args[key.slice(2)] = value;
  }
  return args;
}

function requestShape(url) {
  try {
    const parsed = new URL(url);
    const q = JSON.parse(parsed.searchParams.get("q"));
    return {
      id: q.params?.id,
      timeframe: q.params?.timeframe,
      interval: q.params?.interval,
      date_from: q.params?.date_from,
      date_to: q.params?.date_to,
      count: q.params?.count,
      demo: q.params?.demo,
    };
  } catch {
    return null;
  }
}

async function visibleTextInventory(page) {
  return page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 2 && rect.height > 2 && style.display !== "none" && style.visibility !== "hidden";
    };
    const values = [...document.querySelectorAll('button, a, [role="button"], [role="option"], li, span, div')]
      .filter(visible)
      .map((element) => element.textContent?.replace(/\s+/g, " ").trim())
      .filter((text) => text && text.length <= 60)
      .filter((text) => /мин|час|днев|недел|месяц|тик|сек|minute|hour|day|week|month/i.test(text));
    return [...new Set(values)].slice(0, 100);
  });
}

async function clickExactVisibleText(page, text) {
  return page.evaluate((target) => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 2 && rect.height > 2 && style.display !== "none" && style.visibility !== "hidden";
    };
    const candidates = [...document.querySelectorAll('button, a, [role="button"], [role="option"], li, span, div')]
      .filter(visible)
      .filter((element) => element.textContent?.replace(/\s+/g, " ").trim() === target)
      .sort((left, right) => left.getBoundingClientRect().width - right.getBoundingClientRect().width);
    const element = candidates[0];
    if (!element) return { clicked: false };
    element.click();
    return {
      clicked: true,
      tag: element.tagName,
      id: element.id || null,
      class: typeof element.className === "string" ? element.className.slice(0, 200) : null,
    };
  }, text);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  for (const key of ["config", "chrome", "output-dir"]) {
    if (!args[key]) throw new Error(`--${key} is required`);
  }
  const config = JSON.parse(await fs.readFile(args.config, "utf8"));
  const profile = config.profiles.find((item) => item.id === "desktop_broadband");
  if (!profile) throw new Error("Desktop profile is missing");

  await fs.mkdir(args["output-dir"], { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: args.chrome,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking"],
  });
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setUserAgent(profile.user_agent);
  await page.setViewport(profile.viewport);
  await page.setCacheEnabled(false);

  const getHlocRequests = [];
  page.on("response", (response) => {
    if (response.url().includes("getHloc")) {
      getHlocRequests.push({
        status: response.status(),
        url: response.url(),
        shape: requestShape(response.url()),
        observed_at: new Date().toISOString(),
      });
    }
  });

  let navigationError = null;
  try {
    await page.goto(config.target_url, { waitUntil: "domcontentloaded", timeout: 90_000 });
  } catch (error) {
    navigationError = String(error?.stack || error);
  }
  const firstDeadline = Date.now() + 35_000;
  while (getHlocRequests.length < 1 && Date.now() < firstDeadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  await new Promise((resolve) => setTimeout(resolve, 1500));
  await page.screenshot({ path: path.join(args["output-dir"], "before-dropdown.png"), fullPage: true });

  const opener = await clickExactVisibleText(page, "Дневной");
  await new Promise((resolve) => setTimeout(resolve, 1000));
  const menuTexts = await visibleTextInventory(page);
  await page.screenshot({ path: path.join(args["output-dir"], "dropdown-open.png"), fullPage: true });

  const preferences = [
    "Часовой",
    "1 час",
    "60 минут",
    "Пятиминутный",
    "5 минут",
    "Недельный",
    "Месячный",
  ];
  const selectedText = preferences.find((value) => menuTexts.includes(value)) ||
    menuTexts.find((value) => value !== "Дневной") ||
    null;
  const option = selectedText ? await clickExactVisibleText(page, selectedText) : { clicked: false };

  if (option.clicked) {
    const secondDeadline = Date.now() + 35_000;
    while (getHlocRequests.length < 2 && Date.now() < secondDeadline) {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  await page.screenshot({ path: path.join(args["output-dir"], "after-transition.png"), fullPage: true });

  const selectedState = await page.evaluate(() => {
    const text = document.body?.innerText || "";
    return {
      has_chart_surface: [...document.querySelectorAll('canvas, svg, [id*="chart" i], [class*="chart" i]')]
        .some((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return rect.width >= 120 && rect.height >= 80 && style.display !== "none" && style.visibility !== "hidden";
        }),
      visible_interval_texts: [...new Set(text.split(/\n+/).map((line) => line.trim()).filter((line) => /мин|час|днев|недел|месяц/i.test(line)))].slice(0, 30),
    };
  });

  const initial = getHlocRequests[0]?.shape || null;
  const transitioned = getHlocRequests[1]?.shape || null;
  const requestChanged = Boolean(
    initial && transitioned &&
    (initial.timeframe !== transitioned.timeframe || initial.interval !== transitioned.interval || initial.date_from !== transitioned.date_from)
  );
  const verdict = navigationError
    ? "EVIDENCE_FAILURE"
    : !opener.clicked
      ? "INTERVAL_CONTROL_NOT_FOUND"
      : !selectedText || !option.clicked
        ? "MENU_DISCOVERED_NO_ALTERNATIVE_SELECTED"
        : getHlocRequests.length < 2
          ? "UI_CHANGED_WITHOUT_NEW_HLOC"
          : requestChanged
            ? "TRANSITION_OBSERVED"
            : "STALE_REQUEST_SHAPE";

  const result = {
    schema_version: "liminalqa-chart-timeframe-transition-v1",
    target_url: config.target_url,
    verdict,
    navigation_error: navigationError,
    opener,
    menu_texts: menuTexts,
    selected_text: selectedText,
    option,
    get_hloc_requests: getHlocRequests,
    request_changed: requestChanged,
    selected_state: selectedState,
    generated_at: new Date().toISOString(),
  };
  await fs.writeFile(
    path.join(args["output-dir"], "timeframe-transition-result.json"),
    `${JSON.stringify(result, null, 2)}\n`
  );
  const lines = [
    "# Tradernet chart timeframe transition",
    "",
    `**Verdict:** ${verdict}  `,
    `**Selected option:** ${selectedText ?? "n/a"}  `,
    `**getHloc responses:** ${getHlocRequests.length}`,
    "",
    "| Phase | Timeframe | Interval | Date from | Date to | Status |",
    "|---|---:|---|---|---|---:|",
    ...getHlocRequests.slice(0, 3).map((request, index) =>
      `| ${index === 0 ? "Initial" : "After switch"} | ${request.shape?.timeframe ?? "n/a"} | ${request.shape?.interval ?? "n/a"} | ${request.shape?.date_from ?? "n/a"} | ${request.shape?.date_to ?? "n/a"} | ${request.status} |`
    ),
    "",
  ];
  await fs.writeFile(path.join(args["output-dir"], "timeframe-transition-summary.md"), lines.join("\n"));

  await context.close();
  await browser.close();
  console.log(JSON.stringify(result, null, 2));
  if (verdict === "EVIDENCE_FAILURE") process.exitCode = 1;
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
