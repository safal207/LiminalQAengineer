'use strict';

const isDesktop = process.env.LH_PROFILE === 'desktop';

module.exports = {
  ci: {
    collect: {
      // Serial public-page audit: 5 URLs × 3 runs per profile.
      url: [
        'https://www.duolingo.com/',
        'https://www.duolingo.com/log-in',
        'https://www.duolingo.com/register',
        'https://tr.duolingo.com/imprint',
        'https://www.duolingo.com/share-direct/sm',
      ],
      numberOfRuns: 3,
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
      /*
       * External-target policy:
       * - assertions generate evidence and WARN signals;
       * - Lighthouse is not allowed to issue the final BLOCK verdict;
       * - Lotus/Pythia decides after checking repeatability and environment.
       */
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

        // Initial LiminalQA warning thresholds, not universal truth.
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

        // High-value structural signals.
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

    // Reports remain local. The adapter copies .lighthouseci into Evidence DB.
    upload: {
      target: 'filesystem',
      outputDir: './artifacts/lighthouse',
    },
  },
};
