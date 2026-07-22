import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import process from 'node:process';

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith('--')) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));
const hash = (value) => crypto.createHash('sha256').update(value).digest('hex');

function candidate({id, title, claim, severity, confidence, traces, evidence, alternatives, next}) {
  return {
    finding_id: id,
    title,
    claim_level: claim,
    severity,
    confidence,
    reproduction_status: 'REPRODUCED',
    trace_refs: traces,
    evidence_refs: evidence,
    causal_parent: null,
    competing_explanations: alternatives,
    impact_class: 'QUALITATIVE',
    next_discriminating_test: next,
    authority_boundary: 'Public evidence only; human review is required before external reporting, remediation, deployment, or merge.',
  };
}

function main() {
  if (!args.output) throw new Error('Usage: --output <report-directory>');
  const output = path.resolve(args.output);
  const packetPath = path.join(output, 'causal-packet.json');
  const observationsPath = path.join(output, 'raw-observations.json');
  const packet = JSON.parse(fs.readFileSync(packetPath, 'utf8'));
  const observations = JSON.parse(fs.readFileSync(observationsPath, 'utf8'));
  const by = (target, profile) => observations.find((item) => item.target_id === target && item.profile_id === profile);

  if (observations.length !== 16) throw new Error(`Expected 16 observations, got ${observations.length}`);
  if (by('terms', 'desktop')?.navigation?.status !== 200 || by('terms', 'mobile')?.navigation?.status !== 200) {
    throw new Error('Correct Terms route did not return HTTP 200 in both profiles');
  }

  const desktopOverflow = by('platform', 'desktop')?.state?.horizontal_overflow_px || 0;
  const mobileOverflow = by('platform', 'mobile')?.state?.horizontal_overflow_px || 0;
  const responsiveReproduced = desktopOverflow > 200 && mobileOverflow > 200;
  const homeDesktopUnnamed = by('home', 'desktop')?.accessibility?.unnamed_interactive_count || 0;
  const homeMobileUnnamed = by('home', 'mobile')?.accessibility?.unnamed_interactive_count || 0;
  const platformDesktopUnnamed = by('platform', 'desktop')?.accessibility?.unnamed_interactive_count || 0;
  const accessibilityReproduced = homeDesktopUnnamed > 20 && homeMobileUnnamed > 20 && platformDesktopUnnamed > 20;

  if (!responsiveReproduced) throw new Error(`Responsive overflow discriminator not met: desktop=${desktopOverflow}, mobile=${mobileOverflow}`);
  if (!accessibilityReproduced) throw new Error(`Accessibility discriminator not met: home=${homeDesktopUnnamed}/${homeMobileUnnamed}, platform=${platformDesktopUnnamed}`);

  packet.findings = packet.findings.filter((item) => !['TP-RESPONSIVE-07', 'TP-A11Y-NAME-08'].includes(item.finding_id));
  packet.findings.push(candidate({
    id: 'TP-RESPONSIVE-07',
    title: 'Platform template page creates multi-viewport horizontal overflow on desktop and mobile',
    claim: 'CONFIRMED_DEFECT',
    severity: 'HIGH',
    confidence: 0.99,
    traces: ['platform:desktop', 'platform:mobile'],
    evidence: ['EV-platform-desktop', 'EV-platform-mobile'],
    alternatives: ['intentional horizontal gallery extends the document root', 'decorative background layer controls scroll width', 'headless rendering differs from supported browsers'],
    next: 'Identify the widest visible DOM element and constrain it without reducing the intended template gallery.',
  }));
  packet.findings.push(candidate({
    id: 'TP-A11Y-NAME-08',
    title: 'Public discovery surfaces expose large numbers of unnamed interactive accessibility nodes',
    claim: 'DEFECT_CANDIDATE',
    severity: 'HIGH',
    confidence: 0.94,
    traces: ['home:desktop', 'home:mobile', 'platform:desktop'],
    evidence: ['EV-home-desktop', 'EV-home-mobile', 'EV-platform-desktop'],
    alternatives: ['ignored or duplicate accessibility nodes are included', 'controls receive names after interaction', 'custom widgets expose semantics through another relationship'],
    next: 'Resolve sampled interactive nodes to DOM controls and verify accessible names with keyboard and screen-reader traversal.',
  }));

  const reproduced = packet.findings.filter((item) => item.reproduction_status === 'REPRODUCED').length;
  packet.verdict.state = 'CONFIRMED_DEFECT';
  packet.verdict.gate = 'ESCALATE';
  packet.verdict.summary = `16/16 observations completed; ${reproduced} findings reproduced. Historical memory selected tests but did not authorize this verdict.`;
  packet.next_action.class = 'HUMAN_ADJUDICATION';
  packet.next_action.action = 'Review the reproduced freshness, responsive, accessibility and public trust signals, then select the smallest bounded remediation experiments.';
  fs.writeFileSync(packetPath, `${JSON.stringify(packet, null, 2)}\n`);

  const summary = [
    '# TakeProfit causal deep-audit rerun', '',
    `- Audit: \`${packet.audit_id}\``,
    `- Generated: \`${packet.generated_at}\``,
    `- Source head: \`${packet.source_identity.head_sha}\``,
    `- Run: \`${packet.source_identity.run_id}\` attempt \`${packet.source_identity.run_attempt}\``,
    '- Coverage: `16/16`',
    `- Verdict: \`${packet.verdict.state}\` / \`${packet.verdict.gate}\``, '',
    '| ID | Status | Severity | Claim | Title |',
    '|---|---|---|---|---|',
    ...packet.findings.map((item) => `| ${item.finding_id} | ${item.reproduction_status} | ${item.severity} | ${item.claim_level} | ${item.title} |`), '',
    'PR #87 selected tests; only this exact run controls current status.', '',
  ].join('\n');
  fs.writeFileSync(path.join(output, 'summary.md'), summary);

  const files = [];
  const walk = (directory) => fs.readdirSync(directory, {withFileTypes: true}).forEach((entry) => {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(absolute);
    else if (entry.name !== 'SHA256SUMS') files.push(absolute);
  });
  walk(output);
  fs.writeFileSync(path.join(output, 'SHA256SUMS'), `${files.sort().map((file) => `${hash(fs.readFileSync(file))}  ${path.relative(output, file)}`).join('\n')}\n`);
  console.log(JSON.stringify({desktopOverflow, mobileOverflow, homeDesktopUnnamed, homeMobileUnnamed, platformDesktopUnnamed, reproduced}, null, 2));
}

main();
