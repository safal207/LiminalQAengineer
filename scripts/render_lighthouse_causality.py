#!/usr/bin/env python3
"""Render a Lighthouse causality JSON packet as dynamic Markdown."""
import argparse
import json
from pathlib import Path


def node(graph, node_id):
    return next(item for item in graph["nodes"] if item["id"] == node_id)


def ms(value):
    return "n/a" if value is None else f"{value:,.0f} ms"


def render(graph):
    evidence = graph["evidence"]
    redirect = node(graph, "redirect")["metrics"]
    document = node(graph, "document")["time_ms"]
    css = node(graph, "css")["metrics"]
    lcp = node(graph, "lcp")["metrics"]
    js = node(graph, "js")["metrics"]
    layout = node(graph, "layout")["metrics"]
    contrast = node(graph, "contrast")["metrics"]["elements"]
    error = node(graph, "require_error")["metrics"].get("description") or "not captured"
    mobile_time = node(graph, "hero_dupe")["time_ms"].get("mobile")
    desktop_time = node(graph, "hero_dupe")["time_ms"].get("desktop")
    font_time = node(graph, "layout")["time_ms"]

    lcp_seconds = (lcp.get("lcp_ms") or 0) / 1000
    final_html_seconds = (document.get("end") or 0) / 1000
    redirect_ms = redirect.get("observed_ms")
    css_ms = css.get("modelled_savings_ms")
    cls = layout.get("cls")

    lines = [
        "# LiminalQA · Tradernet space-time causality graph",
        "",
        f"**Target:** `{graph['target']}`  ",
        f"**Evidence SHA-256:** `{evidence['sha256']}`  ",
        f"**Runs in packet:** {graph['run_count']}",
        "",
        "```mermaid",
        "flowchart LR",
        f"  A[\"navigation\"] --> B[\"redirect +{redirect_ms:.0f} ms\"] --> C[\"final HTML ~{final_html_seconds:.2f} s\"]",
        f"  C --> D[\"render-blocking CSS ~{css_ms:.0f} ms potential\"] --> G[\"LCP {lcp_seconds:.1f} s\"]",
        "  C --> E[\"RequireJS + app bootstrap\"] --> F[\"LCP not initially discoverable\"] --> G",
        f"  E --> J[\"{js.get('requests')} scripts / {js.get('transfer_kib')} KiB / ~965 KiB unused\"] --> Q[\"LiminalQA WARN\"]",
        "  M[\"mobile hero early\"] --> N[\"desktop hero later\"]",
        "  N -. possible reconciliation .-> F",
        f"  U[\"unsized subhero + font\"] --> V[\"CLS {cls}\"] --> Q",
        "  W[\"low contrast copy + CTA\"] --> Q",
        "  R[\"require is not defined\"] --> Q",
        "  G --> Q",
        "```",
        "",
        "## Dominant path",
        "",
        f"`navigation → redirect → HTML → runtime bootstrap → late LCP discovery → LCP {lcp_seconds:.1f} s → WARN`",
        "",
        "## Ranked causes",
        "",
        "| Rank | Cause | Status | Why | Next test |",
        "|---:|---|---|---|---|",
    ]
    for item in graph["ranked_causes"]:
        lines.append(f"| {item['rank']} | {item['cause']} | {item['status']} | {item['why']} | {item['next_test']} |")

    lines += [
        "",
        "## Space map",
        "",
        "| Layer | Problem | Effect |",
        "|---|---|---|",
        "| Edge | Language redirect | Delays every cold visit |",
        "| Document | Blocking CSS | Delays visual construction |",
        "| Runtime | Broad bundles + RequireJS | Transfer and CPU waste |",
        "| Responsive media | Both hero variants load | Extra bytes; possible late reconciliation |",
        "| Above fold | Late hero + contrast failures | Slow and less readable first impression |",
        "| Below fold | Unsized image + font | Layout shifts |",
        "",
        "## Time facts",
        "",
        "| Event | Time | Class |",
        "|---|---:|---|",
        f"| Redirect added | {ms(redirect_ms)} | observed |",
        f"| Final HTML completes | {ms(document.get('end'))} | observed |",
        f"| Mobile hero begins | {ms(mobile_time)} | observed |",
        f"| Desktop/LCP hero begins | {ms(desktop_time)} | observed |",
        f"| Font begins | {ms(font_time)} | observed |",
        f"| LCP | {ms(lcp.get('lcp_ms'))} | simulated mobile metric |",
        "",
        "## Concrete defects",
        "",
        f"- Runtime: `{error.replace(chr(10), ' ')}`",
        f"- Contrast failures: **{len(contrast)}** elements, including the primary CTA.",
        f"- Scripts: **{js.get('requests')}** requests, **{js.get('transfer_kib')} KiB**, ~965 KiB estimated unused.",
        "- Both mobile and desktop hero variants transfer in one mobile navigation.",
        "",
        "## Proven vs hypothesis",
        "",
        "**Confirmed:** redirect, non-initial LCP discovery, duplicate hero transfer, unused JS, blocking CSS, runtime error, layout causes, contrast failures.",
        "",
        "**Hypotheses:** hydration replaces the hero; RequireJS error breaks a visible action; timing remains stable across days and regions.",
        "",
        "## Reflection",
        "",
        "The server is not the main bottleneck in this trace. Highest leverage: remove the redirect, expose the correct responsive LCP image in initial HTML, and avoid bootstrapping the broad trading application before landing content stabilizes.",
        "",
        "> Passive public-page evidence only. No authentication, trades, fuzzing, load testing, private data, or vulnerability claim.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    graph = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(render(graph), encoding="utf-8")


if __name__ == "__main__":
    main()
