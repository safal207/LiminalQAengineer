#!/usr/bin/env python3
"""Apply the verified Codex review fixes for PR #54, then self-delete via workflow."""

from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def replace_all(path: str, old: str, new: str, expected: int) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} matches, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def regex_once(path: str, pattern: str, replacement: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    rendered, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"{path}: expected one regex match, found {count}")
    file.write_text(rendered, encoding="utf-8")


def main() -> None:
    domain = ".github/workflows/tradernet-domain-portfolio.yml"
    replace_all(
        domain,
        "        uses: actions/checkout@v6\n",
        "        uses: actions/checkout@v6\n        with:\n          persist-credentials: false\n",
        3,
    )
    replace_once(
        domain,
        '            ([.targets[].url | startswith("https://")] | all)\n',
        '            ([.targets[].url | startswith("https://")] | all) and\n'
        '            ([.targets[].slug | test("^[a-z0-9][a-z0-9_-]{0,63}$")] | all) and\n'
        '            ([.targets[].slug] as $slugs | ($slugs | length) == ($slugs | unique | length))\n',
    )
    replace_once(
        domain,
        '      LIGHTHOUSE_TARGET_URL: ${{ matrix.url }}\n',
        '      TARGET_SLUG: ${{ matrix.slug }}\n      LIGHTHOUSE_TARGET_URL: ${{ matrix.url }}\n',
    )
    replace_once(
        domain,
        '          jq -e \\\n            --arg slug "${{ matrix.slug }}" \\\n            --arg url "${{ matrix.url }}" \\\n',
        '          [[ "${TARGET_SLUG}" =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]] || { echo "Unsafe target slug" >&2; exit 1; }\n'
        '          jq -e \\\n            --arg slug "${TARGET_SLUG}" \\\n            --arg url "${LIGHTHOUSE_TARGET_URL}" \\\n',
    )
    replace_once(
        domain,
        '          mkdir -p "reports/domain/${{ matrix.slug }}"\n',
        '          mkdir -p "reports/domain/${TARGET_SLUG}"\n',
    )
    replace_once(
        domain,
        '          output="reports/domain/${{ matrix.slug }}"\n',
        '          output="reports/domain/${TARGET_SLUG}"\n',
    )

    lighthouse = ".github/workflows/tradernet-lighthouse.yml"
    replace_once(
        lighthouse,
        "        uses: actions/checkout@v6\n",
        "        uses: actions/checkout@v6\n        with:\n          persist-credentials: false\n",
    )
    replace_once(
        lighthouse,
        '        id: target\n        shell: bash\n        run: |\n',
        '        id: target\n        env:\n          INPUT_TARGET_URL: ${{ github.event.inputs.target_url }}\n        shell: bash\n        run: |\n',
    )
    replace_once(
        lighthouse,
        '          target_url="${{ github.event.inputs.target_url }}"\n',
        '          target_url="${INPUT_TARGET_URL}"\n',
    )

    for workflow in (
        ".github/workflows/tradernet-hero-preload-counterfactual.yml",
        ".github/workflows/tradernet-hero-preload-desktop-counterfactual.yml",
    ):
        replace_once(
            workflow,
            "        uses: actions/checkout@v6\n",
            "        uses: actions/checkout@v6\n        with:\n          persist-credentials: false\n",
        )

    desktop_workflow = ".github/workflows/tradernet-hero-preload-desktop-counterfactual.yml"
    regex_once(
        desktop_workflow,
        r"          # The shared collector has a deliberately stricter mobile-era check that\n"
        r"          # rejects repeated response-stage document events\. Preserve all six raw\n"
        r"          # runs and let the desktop-specific aggregator validate the final DOM,\n"
        r"          # exact LCP resource and at-least-one successful interception\.\n"
        r"          set \+e\n"
        r"(          node scripts/tradernet_hero_preload_experiment_cdp\.mjs \\\n"
        r"            --experiment audits/lighthouse/tradernet/hero-preload-desktop-experiment\.json \\\n"
        r"            --chrome \"\$\{\{ steps\.runtime\.outputs\.chrome \}\}\" \\\n"
        r"            --output-dir reports/hero-preload-desktop\n)"
        r"          collector_status=\$\?\n"
        r"          set -e\n",
        r"\1",
    )
    replace_once(
        desktop_workflow,
        '          echo "Shared collector exit status: ${collector_status}" >> "${GITHUB_STEP_SUMMARY}"\n',
        "",
    )

    replace_once(
        "scripts/lighthouse_to_liminalqa.py",
        '        "confidence": "HIGH",\n',
        '        "confidence": "LOW"\n'
        '        if int(policy.get("number_of_runs", 1)) <= 1\n'
        '        else "MEDIUM",\n',
    )

    desktop_result = "scripts/tradernet_desktop_hero_result.py"
    replace_once(
        desktop_result,
        '''    baseline_initiators = sorted(
        {run["metrics"]["hero_entry"].get("initiatorType") for run in baseline}
    )
''',
        '''    baseline_initiators = sorted(
        {
            value
            for run in baseline
            if isinstance(
                value := run["metrics"]["hero_entry"].get("initiatorType"), str
            )
        }
    )
    all_baseline_initiators_are_links = baseline_initiators == ["link"]
''',
    )
    replace_once(
        desktop_result,
        "    elif abs(hero_start_gain) < 300 and abs(lcp_gain) < 300:\n",
        "    elif (\n"
        "        abs(hero_start_gain) < 300\n"
        "        and abs(lcp_gain) < 300\n"
        "        and all_baseline_initiators_are_links\n"
        "    ):\n",
    )
    replace_once(
        desktop_result,
        '        if int(injection.get("fulfilled_documents", 0)) < 1:\n'
        '            raise ValueError(f"Treatment round {run.get(\'round\')} did not intercept a document")\n',
        '        if int(injection.get("fulfilled_documents", 0)) != 1:\n'
        "            raise ValueError(\n"
        '                f"Treatment round {run.get(\'round\')} must intercept exactly one document"\n'
        "            )\n",
    )

    collector = "scripts/tradernet_hero_preload_experiment_cdp.mjs"
    replace_once(
        collector,
        "  const state = { fulfilled: 0, error: null };\n",
        "  const state = { fulfilled: 0, skippedTargetDocuments: 0, error: null };\n",
    )
    replace_once(
        collector,
        '''      if (!isTarget) {
        await client.send("Fetch.continueRequest", { requestId: event.requestId });
        return;
      }
''',
        '''      if (!isTarget || state.fulfilled >= 1) {
        if (isTarget) state.skippedTargetDocuments += 1;
        await client.send("Fetch.continueRequest", { requestId: event.requestId });
        return;
      }
''',
    )
    replace_once(
        collector,
        '''    if (invalid.length > 0) throw new Error(`${variant} produced ${invalid.length} invalid runs`);
    if (
''',
        '''    if (invalid.length > 0) throw new Error(`${variant} produced ${invalid.length} invalid runs`);
    const wrongHeroIdentity = runs.filter(
      (run) =>
        run.metrics.lcp_entry?.url !== experiment.hero_url ||
        run.metrics.hero_entry?.name !== experiment.hero_url
    );
    if (wrongHeroIdentity.length > 0) {
      throw new Error(
        `${variant} produced ${wrongHeroIdentity.length} runs where the configured hero was not both the timed resource and LCP resource`
      );
    }
    if (
''',
    )

    doc = "docs/audits/TRADERNET_LIGHTHOUSE.md"
    replace_once(
        doc,
        '''The policy currently permits only:

- `https://tradernet.ru/`
- `https://tradernet.ru/ideas/`
- `https://tradernet.ru/terminal`

The workflow rejects non-HTTPS origins, custom ports, credentials, query strings, fragments, and paths outside the allowlist.
''',
        '''The single-page workflow currently permits these exact choices:

- `https://tradernet.ru/`
- `https://tradernet.ru/ideas/`
- `https://tradernet.ru/terminal`

The bounded portfolio workflow separately reads six exact targets from `audits/lighthouse/tradernet/domains.json`:

- `https://tradernet.ru/`
- `https://tradernet.com/`
- `https://rc.tradernet.com/faq/13096-how-to-open-an-account-as-an-individual?site_lang=en`
- `https://translate.tradernet.com/`
- `https://tradernet.global/`
- `https://tradernet.am/`

The single-page validator rejects query strings and fragments. The portfolio accepts a query string only when it is part of an exact inventory URL; arbitrary origins, credentials, ports, paths, fragments, and parameters remain outside scope.
''',
    )


if __name__ == "__main__":
    main()
