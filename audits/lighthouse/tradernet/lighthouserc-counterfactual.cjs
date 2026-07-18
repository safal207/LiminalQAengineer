"use strict";

const targetUrl = process.env.LIGHTHOUSE_TARGET_URL;
const outputDir = process.env.LIGHTHOUSE_OUTPUT_DIR;

if (!targetUrl || !outputDir) {
  throw new Error("LIGHTHOUSE_TARGET_URL and LIGHTHOUSE_OUTPUT_DIR are required");
}

module.exports = {
  ci: {
    collect: {
      url: [targetUrl],
      numberOfRuns: 3,
      settings: {
        onlyCategories: ["performance", "accessibility", "best-practices", "seo"],
        chromeFlags: "--headless --no-sandbox --disable-dev-shm-usage"
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
      outputDir
    }
  }
};
