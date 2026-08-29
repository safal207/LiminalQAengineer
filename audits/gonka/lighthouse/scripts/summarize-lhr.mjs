import fs from 'node:fs';
import path from 'node:path';

const [inputDir, outputFile, profile = 'unknown'] = process.argv.slice(2);
if (!inputDir || !outputFile) {
  console.error('Usage: node summarize-lhr.mjs <input-dir> <output-file> [profile]');
  process.exit(2);
}

const walk = dir => fs.existsSync(dir)
  ? fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
      const p = path.join(dir, entry.name);
      return entry.isDirectory() ? walk(p) : [p];
    })
  : [];

const files = walk(inputDir).filter(f => f.endsWith('.json') && !f.endsWith('manifest.json'));
const reports = [];
for (const file of files) {
  try {
    const lhr = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (!lhr.categories || !lhr.audits) continue;
    const score = id => lhr.categories?.[id]?.score == null ? null : Math.round(lhr.categories[id].score * 100);
    const numeric = id => lhr.audits?.[id]?.numericValue ?? null;
    const failedAudits = Object.values(lhr.audits)
      .filter(a => a && typeof a.score === 'number' && a.score < 1 && !['manual','notApplicable','informative'].includes(a.scoreDisplayMode))
      .sort((a,b) => (a.score ?? 1) - (b.score ?? 1))
      .slice(0, 30)
      .map(a => ({id: a.id, title: a.title, score: a.score, displayValue: a.displayValue ?? null}));
    reports.push({
      file,
      requestedUrl: lhr.requestedUrl ?? null,
      finalUrl: lhr.finalDisplayedUrl ?? lhr.finalUrl ?? null,
      fetchTime: lhr.fetchTime ?? null,
      lighthouseVersion: lhr.lighthouseVersion ?? null,
      userAgent: lhr.userAgent ?? null,
      scores: {
        performance: score('performance'),
        accessibility: score('accessibility'),
        bestPractices: score('best-practices'),
        seo: score('seo'),
      },
      metrics: {
        fcpMs: numeric('first-contentful-paint'),
        lcpMs: numeric('largest-contentful-paint'),
        tbtMs: numeric('total-blocking-time'),
        cls: numeric('cumulative-layout-shift'),
        speedIndexMs: numeric('speed-index'),
      },
      runWarnings: lhr.runWarnings ?? [],
      failedAudits,
    });
  } catch (error) {
    console.error(`Skipping ${file}: ${error.message}`);
  }
}

const median = values => {
  const v = values.filter(Number.isFinite).sort((a,b) => a-b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m-1] + v[m]) / 2;
};

const groups = {};
for (const report of reports) {
  const key = report.requestedUrl ?? report.finalUrl ?? 'unknown';
  (groups[key] ??= []).push(report);
}
const urls = Object.entries(groups).map(([url, runs]) => ({
  url,
  runCount: runs.length,
  medians: {
    performance: median(runs.map(r => r.scores.performance)),
    accessibility: median(runs.map(r => r.scores.accessibility)),
    bestPractices: median(runs.map(r => r.scores.bestPractices)),
    seo: median(runs.map(r => r.scores.seo)),
    fcpMs: median(runs.map(r => r.metrics.fcpMs)),
    lcpMs: median(runs.map(r => r.metrics.lcpMs)),
    tbtMs: median(runs.map(r => r.metrics.tbtMs)),
    cls: median(runs.map(r => r.metrics.cls)),
  },
  runs,
}));

const output = {
  schema: 'liminalqa.gonka-lighthouse-summary.v1',
  profile,
  generatedAt: new Date().toISOString(),
  evidenceStatus: reports.length ? 'LHR_AVAILABLE' : 'NO_VALID_LHR',
  reportCount: reports.length,
  urls,
};
fs.mkdirSync(path.dirname(outputFile), {recursive: true});
fs.writeFileSync(outputFile, JSON.stringify(output, null, 2) + '\n');
console.log(`${output.evidenceStatus}: ${reports.length} report(s) -> ${outputFile}`);
