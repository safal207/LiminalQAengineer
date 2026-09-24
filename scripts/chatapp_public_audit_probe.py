#!/usr/bin/env python3
"""Bounded passive public-content probe for the ChatApp outside-in audit."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SCHEMA = "liminalqa-chatapp-public-audit-v1"
RESULT_SCHEMA = "liminalqa-chatapp-public-audit-result-v1"
DEFAULT_CONTRACT = Path("audits/chatapp/public-audit-v0.1/contract.json")


class VisibleTextParser(HTMLParser):
    EXCLUDED = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.excluded_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.EXCLUDED:
            self.excluded_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.EXCLUDED and self.excluded_depth:
            self.excluded_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.excluded_depth == 0:
            self.parts.append(data)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_origin(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme == "https" and parsed.port in (None, 443):
        return f"https://{parsed.hostname}"
    return f"{parsed.scheme}://{parsed.netloc}"


class BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, expected_origin: str) -> None:
        super().__init__()
        self.expected_origin = expected_origin

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        resolved = urllib.parse.urljoin(req.full_url, newurl)
        if canonical_origin(resolved) != self.expected_origin:
            raise urllib.error.HTTPError(
                resolved, code, f"Redirect outside bounded origin: {resolved}", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported ChatApp audit schema")
    origin = (contract.get("target") or {}).get("canonical_origin")
    if origin != "https://chatapp.online":
        raise ValueError("Canonical origin must be exactly https://chatapp.online")

    boundaries = contract.get("boundaries") or {}
    for key in ("public_pages_only", "natural_get_navigation_only"):
        if boundaries.get(key) is not True:
            raise ValueError(f"Boundary {key} must be true")
    for key in (
        "authentication",
        "form_submission",
        "button_clicks",
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
    ):
        if boundaries.get(key) is not False:
            raise ValueError(f"Boundary {key} must be false")

    runtime = contract.get("runtime") or {}
    if runtime.get("max_parallel") != 1:
        raise ValueError("The audit must remain sequential")
    if not isinstance(runtime.get("timeout_seconds"), int) or runtime["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds must be positive")
    if not isinstance(runtime.get("max_response_bytes"), int) or runtime["max_response_bytes"] <= 0:
        raise ValueError("max_response_bytes must be positive")

    allowed = set(contract.get("allowed_paths") or [])
    targets = contract.get("targets") or []
    if not 1 <= len(targets) <= 12:
        raise ValueError("Target count must be between 1 and 12")

    refs: set[str] = set()
    slugs: set[str] = set()
    for target in targets:
        slug = target.get("slug")
        if not slug or slug in slugs:
            raise ValueError(f"Target slug must be unique: {slug!r}")
        slugs.add(slug)
        raw_url = target.get("url")
        parsed = urllib.parse.urlsplit(raw_url)
        if parsed.scheme != "https" or canonical_origin(raw_url) != origin:
            raise ValueError(f"Target outside bounded HTTPS origin: {raw_url}")
        if parsed.query or parsed.fragment:
            raise ValueError(f"Target must not include query or fragment: {raw_url}")
        if (parsed.path or "/") not in allowed:
            raise ValueError(f"Target path is not allowlisted: {parsed.path}")
        assertions = target.get("assertions") or []
        if not assertions:
            raise ValueError(f"Target has no assertions: {slug}")
        for assertion in assertions:
            assertion_id = assertion.get("id")
            ref = f"{slug}:{assertion_id}"
            if not assertion_id or ref in refs:
                raise ValueError(f"Invalid or duplicate assertion: {ref}")
            refs.add(ref)
            kind = assertion.get("type")
            if kind not in {"all_of", "any_of", "occurrence"}:
                raise ValueError(f"Unsupported assertion type: {ref}")
            if kind in {"all_of", "any_of"} and not assertion.get("markers"):
                raise ValueError(f"Marker assertion has no markers: {ref}")
            if kind == "occurrence" and (
                not assertion.get("marker")
                or not isinstance(assertion.get("min_occurrences"), int)
                or assertion["min_occurrences"] < 1
            ):
                raise ValueError(f"Invalid occurrence assertion: {ref}")

    findings = contract.get("findings") or []
    if not findings:
        raise ValueError("At least one finding is required")
    for finding in findings:
        evidence_refs = finding.get("evidence_refs") or []
        if not evidence_refs or any(ref not in refs for ref in evidence_refs):
            raise ValueError(f"Finding has invalid evidence refs: {finding.get('id')}")


def extract_visible_text(raw_html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(raw_html)
    parser.close()
    return normalize_text(" ".join(parser.parts))


def marker_context(text: str, marker: str, radius: int = 160) -> str | None:
    index = text.casefold().find(marker.casefold())
    if index < 0:
        return None
    return text[max(0, index - radius) : min(len(text), index + len(marker) + radius)]


def evaluate_assertion(assertion: dict[str, Any], visible_text: str) -> dict[str, Any]:
    case_sensitive = bool(assertion.get("case_sensitive", False))
    corpus = visible_text if case_sensitive else visible_text.casefold()
    if assertion["type"] in {"all_of", "any_of"}:
        markers = []
        for marker in assertion["markers"]:
            needle = marker if case_sensitive else marker.casefold()
            markers.append(
                {
                    "marker": marker,
                    "present": needle in corpus,
                    "context": marker_context(visible_text, marker),
                }
            )
        passed = all(item["present"] for item in markers)
        if assertion["type"] == "any_of":
            passed = any(item["present"] for item in markers)
        return {"id": assertion["id"], "type": assertion["type"], "passed": passed, "markers": markers}

    marker = assertion["marker"]
    needle = marker if case_sensitive else marker.casefold()
    count = corpus.count(needle)
    return {
        "id": assertion["id"],
        "type": "occurrence",
        "passed": count >= assertion["min_occurrences"],
        "marker": marker,
        "observed_occurrences": count,
        "min_occurrences": assertion["min_occurrences"],
        "context": marker_context(visible_text, marker),
    }


def observe_target(contract: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    runtime = contract["runtime"]
    origin = contract["target"]["canonical_origin"]
    opener = urllib.request.build_opener(BoundedRedirectHandler(origin))
    request = urllib.request.Request(
        target["url"],
        method="GET",
        headers={
            "User-Agent": runtime["user_agent"],
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with opener.open(request, timeout=runtime["timeout_seconds"]) as response:
            body = response.read(runtime["max_response_bytes"] + 1)
            if len(body) > runtime["max_response_bytes"]:
                raise ValueError("Response exceeded max_response_bytes")
            final_url = response.geturl()
            status = getattr(response, "status", None)
            content_type = response.headers.get("Content-Type", "")
        charset_match = re.search(r"charset=([\w.-]+)", content_type, re.I)
        charset = charset_match.group(1) if charset_match else "utf-8"
        try:
            raw_html = body.decode(charset, errors="replace")
        except LookupError:
            raw_html = body.decode("utf-8", errors="replace")
        visible_text = extract_visible_text(raw_html)
        return {
            "slug": target["slug"],
            "requested_url": target["url"],
            "final_url": final_url,
            "status": status,
            "error": None,
            "origin_stayed_bounded": canonical_origin(final_url) == origin,
            "response_bytes": len(body),
            "body_sha256": sha256_bytes(body),
            "visible_text_sha256": sha256_bytes(visible_text.encode("utf-8")),
            "visible_text_length": len(visible_text),
            "visible_text_sample": visible_text[:5000],
            "assertions": [evaluate_assertion(item, visible_text) for item in target["assertions"]],
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {
            "slug": target["slug"],
            "requested_url": target["url"],
            "final_url": getattr(exc, "url", None),
            "status": getattr(exc, "code", None),
            "error": str(exc),
            "origin_stayed_bounded": False,
            "response_bytes": 0,
            "body_sha256": None,
            "visible_text_sha256": None,
            "visible_text_length": 0,
            "visible_text_sample": "",
            "assertions": [
                {"id": item["id"], "type": item["type"], "passed": False, "error": "observation_failed"}
                for item in target["assertions"]
            ],
        }


def aggregate(contract: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    index: dict[str, bool] = {}
    for observation in observations:
        healthy = (
            observation["error"] is None
            and observation["origin_stayed_bounded"]
            and isinstance(observation["status"], int)
            and 200 <= observation["status"] < 400
        )
        for assertion in observation["assertions"]:
            index[f"{observation['slug']}:{assertion['id']}"] = healthy and assertion["passed"]

    findings = []
    for finding in contract["findings"]:
        refs = [{"ref": ref, "passed": index.get(ref) is True} for ref in finding["evidence_refs"]]
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
                "root_cause_status": "HYPOTHESIS_ONLY",
                "business_impact_status": "PLAUSIBLE_NOT_MEASURED",
            }
        )

    complete = len(observations) == len(contract["targets"])
    bounded = all(item["origin_stayed_bounded"] for item in observations)
    errors = sum(1 for item in observations if item["error"])
    signal_count = sum(1 for item in findings if item["state"] == "PRODUCT_SIGNAL")
    return {
        "expected_target_count": len(contract["targets"]),
        "observed_target_count": len(observations),
        "complete": complete,
        "all_final_origins_bounded": bounded,
        "observation_error_count": errors,
        "signal_count": signal_count,
        "decision": "NEEDS_EVIDENCE" if not complete or not bounded or errors else ("PRODUCT_SIGNAL" if signal_count else "NO_SIGNAL_OBSERVED"),
        "findings": findings,
    }


def render_summary(packet: dict[str, Any]) -> str:
    aggregate_result = packet["aggregate"]
    lines = [
        "# LiminalQA · ChatApp outside-in audit v0.1",
        "",
        f"**Decision:** `{aggregate_result['decision']}`  ",
        f"**Coverage:** `{aggregate_result['observed_target_count']}/{aggregate_result['expected_target_count']}`  ",
        f"**Product signals:** `{aggregate_result['signal_count']}/{len(aggregate_result['findings'])}`  ",
        f"**Source head:** `{packet['execution']['source_head_sha']}`",
        "",
        "## Finding matrix",
        "",
        "| ID | Severity | State | Finding |",
        "|---|---|---|---|",
    ]
    for finding in aggregate_result["findings"]:
        lines.append(f"| {finding['id']} | {finding['severity']} | {finding['state']} | {finding['title']} |")
    lines.extend([
        "",
        "## Judgment boundary",
        "",
        "> Public marker reproduction is a product signal, not proof of internal root cause or measured commercial loss.",
        "> No authentication, form submission, direct API testing, security testing, external contact, deployment, or merge is authorized.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/chatapp/public-audit-v0.1"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    contract = load_json(args.contract)
    validate_contract(contract)
    if args.validate_only:
        print("ChatApp audit contract is valid")
        return

    observations = [observe_target(contract, target) for target in contract["targets"]]
    packet = {
        "schema_version": RESULT_SCHEMA,
        "audit_id": contract["audit_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": contract["target"],
        "boundaries": contract["boundaries"],
        "coordinate_model": contract["coordinate_model"],
        "execution": {
            "run_id": os.getenv("GITHUB_RUN_ID"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
            "source_head_sha": os.getenv("GITHUB_HEAD_SHA") or os.getenv("GITHUB_SHA") or "local",
            "workflow_sha": os.getenv("GITHUB_SHA") or "local",
            "base_sha": os.getenv("GITHUB_BASE_SHA"),
            "contract_sha256": sha256_bytes(args.contract.read_bytes()),
        },
        "observations": observations,
        "aggregate": aggregate(contract, observations),
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
    (args.output_dir / "result.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = render_summary(packet)
    (args.output_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
