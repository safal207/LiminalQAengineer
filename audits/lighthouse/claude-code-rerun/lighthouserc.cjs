"use strict";

const targetUrl = "https://claude.com/product/claude-code";

module.exports = {
  ci: {
    collect: {
      url: [targetUrl],
      numberOfRuns: 3,
      settings: {
        onlyCategories: ["performance", "accessibility", "best-practices", "seo"],
        formFactor: "mobile",
        throttlingMethod: "devtools",
        throttling: {
          rttMs: 150,
          throughputKbps: 1638.4,
          requestLatencyMs: 0,
          downloadThroughputKbps: 1474.56,
          uploadThroughputKbps: 675,
          cpuSlowdownMultiplier: 4
        },
        screenEmulation: {
          mobile: true,
          width: 390,
          height: 844,
          deviceScaleFactor: 1,
          disabled: false
        },
        emulatedUserAgent: "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
        chromeFlags: "--headless --no-sandbox --disable-dev-shm-usage --disable-background-networking"
      }
    },
    assert: {
      assertions: {
        "categories:performance": "off",
        "categories:accessibility": "off",
        "categories:best-practices": "off",
        "categories:seo": "off"
      }
    },
    upload: {
      target: "filesystem",
      outputDir: "reports/claude-code-rerun/raw"
    }
  }
};
