#!/usr/bin/env python3
"""Bounded passive public-content probe for the Monetka outside-in audit.

Sequential unauthenticated GET requests only. The probe does not authenticate,
submit forms, enter an address, mutate a cart, place an order, test payments,
activate promotions, contact the company, perform security testing, deploy, or
merge.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
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

SCHEMA = "liminalqa-monetka-public-audit-v1"
RESULT_SCHEMA = "liminalqa-monetka-public-audit-result-v1"
DEFAULT_CONTRACT = Path("audits/monetka/public-audit-v0.1/contract.json")


class VisibleTextParser(HTMLParser):
    EXCLUDED = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.EXCLUDED:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.EXCLUDED and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth == 0:
            self.parts.append(data)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def origin(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    port = parsed.port
    default = (parsed.scheme == "https" and port in (None, 443)) or (
        parsed.scheme == "http" and port in (None, 80)
    )
    return f"{parsed.scheme}://{parsed.hostname}" if default else f"{parsed.scheme}://{parsed.hostname}:{port}"


class BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origins: set[str]) -> None:
        super().__init__()
        self.allowed_origins = allowed_origins

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
        if origin(resolved) not in self.allowed_origins:
            raise urllib.error.HTTPError(
                resolved, code, f"Redirect outside bounded origins: {resolved}", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != SCHEMA:
        raise ValueError(f"Unsupported schema: {contract.get('schema_version')!r}")

    target = contract.get("target") or {}
    allowed_origins = set(target.get("allowed_origins") or [])
    required_origins = {
        "https://monetka.ru",
        "https://www.monetka.ru",
        "https://play.google.com",
        "https://apps.apple.com",
    }
    if allowed_origins != required_origins:
        raise ValueError("Allowed origins must match the bounded Monetka surface set")

    boundaries = contract.get("boundaries") or {}
    for key in ("public_pages_only", "natural_get_navigation_only"):
        if boundaries.get(key) is not True:
            raise ValueError(f"Boundary {key} must be true")
    for key in (
        "authentication",
        "form_submission",
        "button_clicks",
        "address_entry",
        "cart_mutation",
        "order_creation",
        "payment_attempt",
        "promo_activation",
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
        raise ValueError("Audit must remain sequential")
    if not isinstance(runtime.get("timeout_seconds"), int) or runtime["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds must be positive")
    if not isinstance(runtime.get("max_response_bytes"), int) or runtime["max_response_bytes"] <= 0:
        raise ValueError("max_response_bytes must be positive")

    allowed_urls = set(contract.get("allowed_urls") or [])
    targets = contract.get("targets") or []
    if not 1 <= len(targets) <= 12:
        raise ValueError("Target count must be between 1 and 12")

    slugs: set[str] = set()
    refs: set[str] = set()
    for item in targets:
        slug = item.get("slug")
        url = item.get("url")
        if not slug or slug in slugs:
            raise ValueError(f"Duplicate or missing target slug: {slug!r}")
        slugs.add(slug)
        if url not in allowed_urls:
            raise ValueError(f"Target URL is not exactly allowlisted: {url}")
        if urllib.parse.urlsplit(url).scheme != "https" or origin(url) not in allowed_origins:
            raise ValueError(f"Target outside bounded HTTPS origins: {url}")
        assertions = item.get("assertions") or []
        if not assertions:
            raise ValueError(f"Target has no assertions: {slug}")
        for assertion in assertions:
            assertion_id = assertion.get("id")
            assertion_type = assertion.get("type")
            if not assertion_id:
                raise ValueError(f"Assertion without id on {slug}")
            ref = f"{slug}:{assertion_id}"
            if ref in refs:
                raise ValueError(f"Duplicate assertion ref: {ref}")
            refs.add(ref)
            if assertion_type not in {"all_of", "any_of", "none_of", "occurrence"}:
                raise ValueError(f"Unsupported assertion type in {ref}")
            if assertion_type in {"all_of", "any_of", "none_of"} and not assertion.get("markers"):
                raise ValueError(f"Marker assertion has no markers: {ref}")
            if assertion_type == "occurrence" and (
                not assertion.get("marker")
                or not isinstance(assertion.get("min_occurrences"), int)
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


def marker_context(text: str, marker: str, radius: int = 180) -> str | None:
    index = text.casefold().find(marker.casefold())
    if index < 0:
        return None
    return text[max(0, index - radius) : min(len(text), index + len(marker) + radius)]


def evaluate_assertion(assertion: dict[str, Any], text: str) -> dict[str, Any]:
    corpus = text if assertion.get("case_sensitive") else text.casefold()
    kind = assertion["type"]
    if kind in {"all_of", "any_of", "none_of"}:
        marker_results = []
        for marker in assertion["markers"]:
            needle = marker if assertion.get("case_sensitive") else marker.casefold()
            present = needle in corpus
            marker_results.append(
                {"marker": marker, "present": present, "context": marker_context(text, marker)}
            )
        if kind == "all_of":
            passed = all(item["present"] for item in marker_results)
        elif kind == "any_of":
            passed = any(item["present"] for item in marker_results)
        else:
            passed = not any(item["present"] for item in marker_results)
        return {"id": assertion["id"], "type": kind, "passed": passed, "markers": marker_results}

    marker = assertion["marker"]
    needle = marker if assertion.get("case_sensitive") else marker.casefold()
    count = corpus.count(needle)
    return {
        "id": assertion["id"],
        "type": "occurrence",
        "passed": count >= assertion["min_occurrences"],
        "marker": marker,
        "observed_occurrences": count,
        "min_occurrences": assertion["min_occurrences"],
        "context": marker_context(text, marker),
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


def failed_observation(target: dict[str, Any], exc: BaseException) -> Observation:
    return Observation(
        slug=target["slug"],
        requested_url=target["url"],
        final_url=getattr(exc, "url", None),
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
            {"id": item["id"], "type": item["type"], "passed": False, "error": "target_observation_failed"}
            for item in target["assertions"]
        ],
    )


def observe(contract: dict[str, Any], target: dict[str, Any]) -> Observation:
    runtime = contract["runtime"]
    allowed_origins = set(contract["target"]["allowed_origins"])
    request = urllib.request.Request(
        target["url"],
        method="GET",
        headers={
            "User-Agent": runtime["user_agent"],
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
        },
    )
    opener = urllib.request.build_opener(BoundedRedirectHandler(allowed_origins))
    try:
        with opener.open(request, timeout=runtime["timeout_seconds"]) as response:
            final_url = response.geturl()
            if origin(final_url) not in allowed_origins:
                raise ValueError(f"Final URL outside bounded origins: {final_url}")
            status = getattr(response, "status", None)
            content_type = response.headers.get("Content-Type")
            body = response.read(runtime["max_response_bytes"] + 1)
            if len(body) > runtime["max_response_bytes"]:
                raise ValueError("Response exceeded max_response_bytes")
        charset = "utf-8"
        match = re.search(r"charset=([\w.-]+)", content_type or "", re.I)
        if match:
            charset = match.group(1)
        try:
            raw_html = body.decode(charset, errors="replace")
        except LookupError:
            raw_html = body.decode("utf-8", errors="replace")
        text = extract_visible_text(raw_html)
        return Observation(
            slug=target["slug"],
            requested_url=target["url"],
            final_url=final_url,
            status=status,
            error=None,
            content_type=content_type,
            response_bytes=len(body),
            body_sha256=sha256_bytes(body),
            visible_text_sha256=sha256_bytes(text.encode("utf-8")),
            visible_text_length=len(text),
            visible_text_sample=text[:12000],
            origin_stayed_bounded=True,
            assertions=[evaluate_assertion(item, text) for item in target["assertions"]],
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return failed_observation(target, exc)


def build_result(contract: dict[str, Any], observations: list[Observation]) -> dict[str, Any]:
    assertion_map: dict[str, bool] = {}
    for observation in observations:
        for assertion in observation.assertions:
            assertion_map[f"{observation.slug}:{assertion['id']}"] = bool(assertion.get("passed"))

    finding_results = []
    for finding in contract["findings"]:
        refs = finding["evidence_refs"]
        passed = all(assertion_map.get(ref, False) for ref in refs)
        state = finding.get("promotion_ceiling") if passed and finding.get("promotion_ceiling") else (
            "PRODUCT_SIGNAL" if passed else "NEEDS_EVIDENCE"
        )
        finding_results.append(
            {
                "id": finding["id"],
                "title": finding["title"],
                "severity": finding["severity"],
                "state": state,
                "evidence_refs": refs,
                "evidence_passed": passed,
                "promotion_ceiling": finding.get("promotion_ceiling"),
                "root_cause": "HYPOTHESIS_ONLY",
                "business_impact": "PLAUSIBLE_NOT_MEASURED",
            }
        )

    return {
        "schema_version": RESULT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_id": contract["audit_id"],
        "target": contract["target"],
        "boundaries": contract["boundaries"],
        "observations": [item.to_dict() for item in observations],
        "aggregate": {
            "expected_target_count": len(contract["targets"]),
            "observed_target_count": len(observations),
            "http_success_count": sum(1 for item in observations if item.status and 200 <= item.status < 300),
            "bounded_origin_count": sum(1 for item in observations if item.origin_stayed_bounded),
            "findings": finding_results,
        },
        "authority": {
            "mode": "evidence_only",
            "grants": {"external_submission": False, "deployment": False, "merge": False},
        },
    }


def write_outputs(output_dir: Path, result: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Monetka outside-in audit v0.1 · raw summary",
        "",
        f"- Generated: `{result['generated_at']}`",
        f"- Routes: `{result['aggregate']['observed_target_count']}/{result['aggregate']['expected_target_count']}`",
        f"- HTTP 2xx: `{result['aggregate']['http_success_count']}`",
        f"- Bounded origins: `{result['aggregate']['bounded_origin_count']}`",
        "",
        "## Findings",
        "",
    ]
    for finding in result["aggregate"]["findings"]:
        lines.append(f"- **{finding['id']}** · {finding['state']} · {finding['severity']} · {finding['title']}")
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/monetka/public-audit-v0.1"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    contract = load_json(args.contract)
    validate_contract(contract)
    if args.validate_only:
        print("Contract valid")
        return 0

    observations = [observe(contract, target) for target in contract["targets"]]
    result = build_result(contract, observations)
    write_outputs(args.output_dir, result)
    print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
