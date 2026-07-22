#!/usr/bin/env python3
"""Bounded passive public-content probe for the Bell Integrator outside-in audit.

The probe performs sequential unauthenticated GET requests only. It records
reproducible public evidence and does not submit forms, authenticate, enumerate,
fuzz, load test, make a vulnerability claim, contact the company, deploy, or merge.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SCHEMA = "liminalqa-bell-integrator-public-audit-v1"
RESULT_SCHEMA = "liminalqa-bell-integrator-public-audit-result-v1"
DEFAULT_CONTRACT = Path("audits/bell-integrator/public-audit-v0.1/contract.json")


class VisibleTextParser(HTMLParser):
    """Extract visible-ish text while excluding scripts, styles, and templates."""

    EXCLUDED = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._excluded_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.EXCLUDED:
            self._excluded_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.EXCLUDED and self._excluded_depth:
            self._excluded_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._excluded_depth == 0:
            self.parts.append(data)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_origin(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url)
    port = parsed.port
    default_port = (parsed.scheme == "https" and port in (None, 443)) or (
        parsed.scheme == "http" and port in (None, 80)
    )
    if not default_port:
        return f"{parsed.scheme}://{parsed.hostname}:{port}"
    return f"{parsed.scheme}://{parsed.hostname}"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != SCHEMA:
        raise ValueError(f"Unsupported schema: {contract.get('schema_version')!r}")

    target = contract.get("target") or {}
    expected_origin = target.get("canonical_origin")
    if expected_origin != "https://bellintegrator.ru":
        raise ValueError("Canonical origin must be exactly https://bellintegrator.ru")

    boundaries = contract.get("boundaries") or {}
    required_true = ["public_pages_only", "natural_get_navigation_only"]
    required_false = [
        "authentication",
        "form_submission",
        "email_or_external_contact",
        "direct_api_testing",
        "active_security_testing",
        "enumeration",
        "fuzzing",
        "load_testing",
        "vulnerability_claim",
        "external_submission_authorized",
        "deployment_authorized",
        "merge_authorized",
    ]
    for key in required_true:
        if boundaries.get(key) is not True:
            raise ValueError(f"Boundary {key} must be true")
    for key in required_false:
        if boundaries.get(key) is not False:
            raise ValueError(f"Boundary {key} must be false")

    runtime = contract.get("runtime") or {}
    if runtime.get("max_parallel") != 1:
        raise ValueError("The audit must remain sequential")
    if not isinstance(runtime.get("timeout_seconds"), int) or runtime["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    if not isinstance(runtime.get("max_response_bytes"), int) or runtime["max_response_bytes"] <= 0:
        raise ValueError("max_response_bytes must be a positive integer")

    allowed_paths = set(contract.get("allowed_paths") or [])
    targets = contract.get("targets") or []
    if not 1 <= len(targets) <= 12:
        raise ValueError("Target count must be between 1 and 12")

    target_slugs: set[str] = set()
    assertion_refs: set[str] = set()
    for item in targets:
        slug = item.get("slug")
        if not slug or slug in target_slugs:
            raise ValueError(f"Target slug must be unique: {slug!r}")
        target_slugs.add(slug)

        raw_url = item.get("url")
        parsed = urllib.parse.urlsplit(raw_url)
        if parsed.scheme != "https" or canonical_origin(raw_url) != expected_origin:
            raise ValueError(f"Target outside bounded HTTPS origin: {raw_url}")
        if parsed.query or parsed.fragment:
            raise ValueError(f"Target must not include query or fragment: {raw_url}")
        if (parsed.path or "/") not in allowed_paths:
            raise ValueError(f"Target path is not allowlisted: {parsed.path}")

        assertions = item.get("assertions") or []
        if not assertions:
            raise ValueError(f"Target has no assertions: {slug}")
        for assertion in assertions:
            assertion_id = assertion.get("id")
            if not assertion_id:
                raise ValueError(f"Assertion without id on {slug}")
            ref = f"{slug}:{assertion_id}"
            if ref in assertion_refs:
                raise ValueError(f"Duplicate assertion reference: {ref}")
            assertion_refs.add(ref)
            if assertion.get("type") not in {"all_of", "any_of", "occurrence"}:
                raise ValueError(f"Unsupported assertion type in {ref}")
            if assertion["type"] in {"all_of", "any_of"} and not assertion.get("markers"):
                raise ValueError(f"Marker assertion has no markers: {ref}")
            if assertion["type"] == "occurrence":
                if not assertion.get("marker") or not isinstance(assertion.get("min_occurrences"), int):
                    raise ValueError(f"Invalid occurrence assertion: {ref}")

    findings = contract.get("findings") or []
    if not findings:
        raise ValueError("At least one finding is required")
    for finding in findings:
        refs = finding.get("evidence_refs") or []
        if not refs or any(ref not in assertion_refs for ref in refs):
            raise ValueError(f"Finding has invalid evidence refs: {finding.get('id')}")


def decode_body(body: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type:
        match = re.search(r"charset=([\w.-]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def extract_visible_text(raw_html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(raw_html)
    parser.close()
    return normalize_text(" ".join(parser.parts))


def marker_context(text: str, marker: str, radius: int = 140) -> str | None:
    index = text.casefold().find(marker.casefold())
    if index < 0:
        return None
    return text[max(0, index - radius) : min(len(text), index + len(marker) + radius)]


def evaluate_assertion(assertion: dict[str, Any], visible_text: str) -> dict[str, Any]:
    case_sensitive = bool(assertion.get("case_sensitive", False))
    corpus = visible_text if case_sensitive else visible_text.casefold()

    if assertion["type"] in {"all_of", "any_of"}:
        marker_results = []
        for marker in assertion["markers"]:
            needle = marker if case_sensitive else marker.casefold()
            marker_results.append(
                {
                    "marker": marker,
                    "present": needle in corpus,
                    "context": marker_context(visible_text, marker),
                }
            )
        passed = (
            all(item["present"] for item in marker_results)
            if assertion["type"] == "all_of"
            else any(item["present"] for item in marker_results)
        )
        return {
            "id": assertion["id"],
            "type": assertion["type"],
            "passed": passed,
            "markers": marker_results,
        }

    marker = assertion["marker"]
    needle = marker if case_sensitive else marker.casefold()
    count = corpus.count(needle)
    return {
        "id": assertion["id"],
        "type": "occurrence",
        "marker": marker,
        "observed_occurrences": count,
        "min_occurrences": assertion["min_occurrences"],
        "passed": count >= assertion["min_occurrences"],
        "context": marker_context(visible_text, marker),
    }


@dataclass
class Observation:
    slug: str
    requested_url: str
    final_url: str | None
    status: int | None
    error: str | None
    content_type: str | None
    response_bytes: int
    body_sha256: str | None
    visible_text_sha256: str | None
    visible_text_length: int
    visible_text_sample: str
    origin_stayed_bounded: bool
    assertions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def observe_target(contract: dict[str, Any], target: dict[str, Any]) -> Observation:
    runtime = contract["runtime"]
    request = urllib.request.Request(
        target["url"],
        method="GET",
        headers={
            "User-Agent": runtime["user_agent"],
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=runtime["timeout_seconds"]) as response:
            final_url = response.geturl()
            status = getattr(response, "status", None)
            content_type = response.headers.get("Content-Type")
            body = response.read(runtime["max_response_bytes"] + 1)
            if len(body) > runtime["max_response_bytes"]:
                raise ValueError("Response exceeded max_response_bytes")

        raw_html = decode_body(body, content_type)
        visible_text = extract_visible_text(raw_html)
        assertions = [evaluate_assertion(item, visible_text) for item in target["assertions"]]
        return Observation(
            slug=target["slug"],
            requested_url=target["url"],
            final_url=final_url,
            status=status,
            error=None,
            content_type=content_type,
            response_bytes=len(body),
            body_sha256=sha256_bytes(body),
            visible_text_sha256=sha256_bytes(visible_text.encode("utf-8")),
            visible_text_length=len(visible_text),
            visible_text_sample=visible_text[:5000],
            origin_stayed_bounded=canonical_origin(final_url) == contract["target"]["canonical_origin"],
            assertions=assertions,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return Observation(
            slug=target["slug"],
            requested_url=target["url"],
            final_url=None,
            status=getattr(exc, "code", None),
            error=str(exc),
            content_type=None,
            response_bytes=0,
            body_sha256=None,
            visible_text_sha256=None,
            visible_text_length=0,
            visible_text_sample="",
            origin_stayed_bounded=False,
            assertions=[
                {
                    "id": item["id"],
                    "type": item["type"],
                    "passed": False,
                    "error": "target_observation_failed",
                }
                for item in target["assertions"]
            ],
        )


def aggregate(contract: dict[str, Any], observations: list[Observation]) -> dict[str, Any]:
    assertion_index: dict[str, bool] = {}
    for observation in observations:
        valid_observation = (
            observation.error is None
            and observation.origin_stayed_bounded
            and observation.status is not None
            and 200 <= observation.status < 400
        )
        for assertion in observation.assertions:
            assertion_index[f"{observation.slug}:{assertion['id']}"] = bool(
                valid_observation and assertion.get("passed") is True
            )

    findings = []
    for finding in contract["findings"]:
        refs = [
            {"ref": ref, "passed": assertion_index.get(ref, False)}
            for ref in finding["evidence_refs"]
        ]
        reproduced = all(item["passed"] for item in refs)
        findings.append(
            {
                "id": finding["id"],
                "title": finding["title"],
                "severity": finding["severity"],
                "state": "PRODUCT_SIGNAL" if reproduced else "NEEDS_EVIDENCE",
                "evidence": refs,
                "quality_lens": finding["quality_lens"],
                "system_lens": finding["system_lens"],
                "business_lens": finding["business_lens"],
                "promotion_rule": finding["promotion_rule"],
                "root_cause_status": "HYPOTHESIS_ONLY",
                "business_impact_status": "PLAUSIBLE_NOT_MEASURED",
            }
        )

    complete = len(observations) == len(contract["targets"])
    bounded = all(item.origin_stayed_bounded for item in observations)
    errors = [item.slug for item in observations if item.error]
    signal_count = sum(item["state"] == "PRODUCT_SIGNAL" for item in findings)
    decision = "NEEDS_EVIDENCE" if errors or not complete or not bounded else (
        "PRODUCT_SIGNAL" if signal_count else "NO_SIGNAL_OBSERVED"
    )
    return {
        "decision": decision,
        "target_count": len(contract["targets"]),
        "observed_target_count": len(observations),
        "complete": complete,
        "all_final_origins_bounded": bounded,
        "error_targets": errors,
        "finding_count": len(findings),
        "product_signal_count": signal_count,
        "findings": findings,
    }


def render_summary(packet: dict[str, Any]) -> str:
    aggregate_result = packet["aggregate"]
    lines = [
        "# LiminalQA · Bell Integrator outside-in audit v0.1",
        "",
        f"**Decision:** `{aggregate_result['decision']}`  ",
        f"**Coverage:** `{aggregate_result['observed_target_count']}/{aggregate_result['target_count']}`  ",
        f"**Product signals:** `{aggregate_result['product_signal_count']}/{aggregate_result['finding_count']}`  ",
        f"**Source head:** `{packet['execution']['source_head_sha']}`",
        "",
        "## Tri-lens finding matrix",
        "",
        "| ID | Severity | State | Claim |",
        "|---|---|---|---|",
    ]
    for finding in aggregate_result["findings"]:
        lines.append(
            f"| {finding['id']} | {finding['severity']} | {finding['state']} | {finding['title']} |"
        )

    lines.extend(["", "## Target evidence", ""])
    for observation in packet["observations"]:
        passed = sum(item.get("passed") is True for item in observation["assertions"])
        lines.append(
            f"- **{observation['slug']}** — HTTP `{observation['status']}`, "
            f"assertions `{passed}/{len(observation['assertions'])}`, "
            f"bounded `{observation['origin_stayed_bounded']}`"
        )

    lines.extend(
        [
            "",
            "## Judgment boundary",
            "",
            "> A public marker match is a product signal, not proof of internal root cause or measured commercial loss.",
            "",
            "> Evidence only. No authentication, form submission, direct API testing, active security testing,",
            "> external contact, delivery, deployment, or merge is authorized.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/bell-integrator/public-audit-v0.1"))
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    contract = load_json(args.contract)
    validate_contract(contract)
    if args.validate_only:
        print(f"Validated {args.contract}")
        return 0

    observations = [observe_target(contract, target) for target in contract["targets"]]
    aggregate_result = aggregate(contract, observations)
    source_head_sha = os.getenv("GITHUB_HEAD_SHA") or os.getenv("GITHUB_SHA") or "local"
    packet = {
        "schema_version": RESULT_SCHEMA,
        "audit_id": contract["audit_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": contract["target"],
        "coordinate_model": contract["coordinate_model"],
        "boundaries": contract["boundaries"],
        "execution": {
            "run_id": os.getenv("GITHUB_RUN_ID"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
            "source_head_sha": source_head_sha,
            "workflow_sha": os.getenv("GITHUB_SHA") or "local",
            "contract_sha256": sha256_bytes(args.contract.read_bytes()),
        },
        "observations": [item.to_dict() for item in observations],
        "aggregate": aggregate_result,
        "authority": {
            "mode": "evidence_only",
            "grants": {
                "ownership": False,
                "approval": False,
                "execution": False,
                "external_submission": False,
                "delivery": False,
                "deployment": False,
                "merge": False,
            },
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "result.json"
    summary_path = args.output_dir / "summary.md"
    result_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = render_summary(packet)
    summary_path.write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
