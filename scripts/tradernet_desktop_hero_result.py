#!/usr/bin/env python3
"""Aggregate six desktop hero-preload browser runs into a LiminalQA packet."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

METRICS = (
    "first_contentful_paint_ms",
    "largest_contentful_paint_ms",
    "hero_request_start_ms",
    "hero_response_end_ms",
    "hero_load_to_lcp_gap_ms",
    "long_task_total_ms",
    "script_transfer_bytes",
    "script_request_count",
    "navigation_response_end_ms",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rounded(value: float | int | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def median_metric(runs: list[dict[str, Any]], metric: str) -> float | None:
    values = [run["metrics"].get(metric) for run in runs]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return rounded(statistics.median(numeric)) if numeric else None


def summarize(runs: list[dict[str, Any]]) -> dict[str, float | None]:
    return {metric: median_metric(runs, metric) for metric in METRICS}


def effect(baseline: float | None, treatment: float | None) -> dict[str, float | None]:
    if baseline is None or treatment is None:
        return {"treatment_minus_baseline": None, "improvement_percent": None}
    difference = treatment - baseline
    improvement = None if baseline == 0 else ((baseline - treatment) / baseline) * 100
    return {
        "treatment_minus_baseline": rounded(difference),
        "improvement_percent": rounded(improvement, 2),
    }


def validate_runs(
    baseline: list[dict[str, Any]],
    treatment: list[dict[str, Any]],
    expected_hero: str,
) -> None:
    if len(baseline) != 3 or len(treatment) != 3:
        raise ValueError(f"Expected 3+3 runs, got {len(baseline)}+{len(treatment)}")

    for label, runs in (("baseline", baseline), ("hero_preload", treatment)):
        for run in runs:
            if run.get("navigation_error"):
                raise ValueError(f"{label} round {run.get('round')} navigation failed")
            metrics = run.get("metrics", {})
            if not isinstance(metrics.get("largest_contentful_paint_ms"), (int, float)):
                raise ValueError(f"{label} round {run.get('round')} has no LCP")
            if metrics.get("lcp_entry", {}).get("url") != expected_hero:
                raise ValueError(f"{label} round {run.get('round')} used another LCP resource")
            if metrics.get("hero_entry", {}).get("name") != expected_hero:
                raise ValueError(f"{label} round {run.get('round')} has no exact hero resource timing")

    for run in treatment:
        injection = run.get("injection", {})
        if injection.get("error"):
            raise ValueError(f"Treatment round {run.get('round')} injection failed")
        if int(injection.get("fulfilled_documents", 0)) != 1:
            raise ValueError(
                f"Treatment round {run.get('round')} must intercept exactly one document"
            )
        if not run.get("metrics", {}).get("preload_present"):
            raise ValueError(f"Treatment round {run.get('round')} has no preload in the final DOM")


def render_markdown(packet: dict[str, Any]) -> str:
    baseline = packet["variants"]["baseline"]["medians"]
    treatment = packet["variants"]["hero_preload"]["medians"]
    effects = packet["effects"]
    labels = {
        "hero_request_start_ms": "Hero request start",
        "hero_response_end_ms": "Hero response end",
        "largest_contentful_paint_ms": "LCP",
        "hero_load_to_lcp_gap_ms": "Hero loaded → LCP gap",
        "first_contentful_paint_ms": "FCP",
        "long_task_total_ms": "Long-task total",
        "script_transfer_bytes": "Script transfer",
        "script_request_count": "Script requests",
    }
    lines = [
        "# LiminalQA · Tradernet desktop-web hero preload counterfactual",
        "",
        f"**Verdict:** `{packet['verdict']}`  ",
        f"**Confidence:** `{packet['confidence']}`  ",
        f"**Runs:** 3 baseline + 3 treatment",
        "",
        "| Metric | Baseline median | Extra preload median | Treatment − baseline | Improvement |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, label in labels.items():
        current = effects[key]
        lines.append(
            f"| {label} | {baseline[key]} | {treatment[key]} | "
            f"{current['treatment_minus_baseline']} | {current['improvement_percent']}% |"
        )
    lines.extend(
        [
            "",
            "## Causal reading",
            "",
            packet["interpretation"],
            "",
            "> Desktop laboratory evidence only. The treatment changed browser-local HTML after the public response and did not modify Tradernet servers.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--experiment", required=True, type=Path)
    args = parser.parse_args()

    experiment = load_json(args.experiment)
    baseline = [load_json(args.input_dir / f"baseline-round-{index}.json") for index in range(1, 4)]
    treatment = [
        load_json(args.input_dir / f"hero_preload-round-{index}.json") for index in range(1, 4)
    ]
    validate_runs(baseline, treatment, experiment["hero_url"])

    baseline_summary = summarize(baseline)
    treatment_summary = summarize(treatment)
    effects = {
        metric: effect(baseline_summary[metric], treatment_summary[metric]) for metric in METRICS
    }

    hero_start_gain = (
        baseline_summary["hero_request_start_ms"] - treatment_summary["hero_request_start_ms"]
    )
    lcp_gain = (
        baseline_summary["largest_contentful_paint_ms"]
        - treatment_summary["largest_contentful_paint_ms"]
    )
    baseline_initiators = sorted(
        {
            value
            for run in baseline
            if isinstance(
                value := run["metrics"]["hero_entry"].get("initiatorType"), str
            )
        }
    )
    all_baseline_initiators_are_links = baseline_initiators == ["link"]

    if hero_start_gain >= 500 and lcp_gain >= 500:
        verdict = "SUPPORTED"
        interpretation = (
            f"The extra preload starts the desktop hero {rounded(hero_start_gain)} ms earlier and "
            f"improves LCP by {rounded(lcp_gain)} ms. Late discovery is material on desktop."
        )
    elif (
        abs(hero_start_gain) < 300
        and abs(lcp_gain) < 300
        and all_baseline_initiators_are_links
    ):
        verdict = "NO_ADDITIONAL_EFFECT"
        interpretation = (
            "The desktop baseline already initiates the exact LCP hero through a link resource hint. "
            f"Adding another preload changes median request start by only {rounded(-hero_start_gain)} ms "
            f"and median LCP by {rounded(-lcp_gain)} ms. The mobile late-discovery defect therefore "
            "does not reproduce in this desktop profile; the remaining desktop delay is dominated by "
            "render/runtime timing rather than missing image preload."
        )
    else:
        verdict = "MIXED_OR_UNSTABLE"
        interpretation = (
            f"The extra preload changes hero request start by {rounded(-hero_start_gain)} ms and LCP "
            f"by {rounded(-lcp_gain)} ms. The effect is not strong enough for a stable causal claim."
        )

    packet = {
        "schema_version": "liminalqa-desktop-counterfactual-result-v1",
        "experiment": experiment,
        "verdict": verdict,
        "confidence": "MEDIUM",
        "baseline_hero_initiator_types": baseline_initiators,
        "variants": {
            "baseline": {"run_count": 3, "medians": baseline_summary, "runs": baseline},
            "hero_preload": {"run_count": 3, "medians": treatment_summary, "runs": treatment},
        },
        "effects": effects,
        "interpretation": interpretation,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "desktop-hero-preload-result.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "desktop-hero-preload-summary.md").write_text(
        render_markdown(packet), encoding="utf-8"
    )
    print(json.dumps({"verdict": verdict, "baseline": baseline_summary, "treatment": treatment_summary}, indent=2))


if __name__ == "__main__":
    main()
