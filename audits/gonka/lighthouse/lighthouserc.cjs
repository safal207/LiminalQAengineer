'use strict';

const isDesktop = process.env.LH_PROFILE === 'desktop';
const requestedRuns = Number.parseInt(process.env.LH_RUNS ?? '3', 10);
const numberOfRuns = Number.isInteger(requestedRuns) && requestedRuns > 0
  ? requestedRuns
  : 3;

module.exports = {
  ci: {
    collect: {
      url: [
        'https://gonka.ai/',
        'https://gonka.ai/docs/',
        'https://gonka.ai/docs/developer/quickstart/',
        'https://gonka.ai/docs/host/quickstart/',
        'https://gonka.ai/docs/report-vulnerability/',
      ],
      numberOfRuns,
      settings: {
        ...(isDesktop ? { preset: 'desktop' } : {}),
        onlyCategories: [
          'performance',
          'accessibility',
          'best-practices',
          'seo',
        ],
        maxWaitForLoad: 90000,
        chromeFlags: '--headless=new --disable-gpu',
      },
    },

    assert: {
      assertions: {
        'categories:performance': [
          'warn',
          { minScore: 0.75, aggregationMethod: 'median' },
        ],
        'categories:accessibility': [
          'warn',
          { minScore: 0.90, aggregationMethod: 'pessimistic' },
        ],
        'categories:best-practices': [
          'warn',
          { minScore: 0.90, aggregationMethod: 'pessimistic' },
        ],
        'categories:seo': [
          'warn',
          { minScore: 0.90, aggregationMethod: 'pessimistic' },
        ],
        'largest-contentful-paint': [
          'warn',
          { maxNumericValue: 4000, aggregationMethod: 'median' },
        ],
        'cumulative-layout-shift': [
          'warn',
          { maxNumericValue: 0.25, aggregationMethod: 'pessimistic' },
        ],
        'total-blocking-time': [
          'warn',
          { maxNumericValue: 600, aggregationMethod: 'median' },
        ],
        'http-status-code': 'warn',
        'errors-in-console': ['warn', { maxLength: 0 }],
        'document-title': 'warn',
        'html-has-lang': 'warn',
        'valid-lang': 'warn',
        'meta-description': 'warn',
        'is-crawlable': 'warn',
        'robots-txt': 'warn',
      },
    },

    upload: {
      target: 'filesystem',
      outputDir: './artifacts/lighthouse',
    },
  },
};
