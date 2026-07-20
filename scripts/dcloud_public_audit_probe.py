#!/usr/bin/env python3
"""Run a bounded passive public-content recheck for the DCloud tri-lens audit."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class BoundedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_origin: str) -> None:
        super().__init__()
        self.allowed_origin = allowed_origin

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        parsed = urlsplit(newurl)
        origin = f"{parsed.scheme}://{parsed.hostname or ''}"
        if origin != self.allowed_origin:
            raise ValueError(f"Redirect left the allowlisted origin: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("Contract must be a JSON object")
    return value


def normalize_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != "liminalqa-tri-lens-public-audit-v1":
        raise ValueError("Unsupported contract schema")
    target = contract.get("target")
    if not isinstance(target, dict):
        raise ValueError("Missing target")
    allowed_origin = target.get("canonical_origin")
    if not isinstance(allowed_origin, str) or not allowed_origin.startswith("https://"):
        raise ValueError("canonical_origin must be HTTPS")

    boundaries = contract.get("boundaries")
    if not isinstance(boundaries, dict):
        raise ValueError("Missing boundaries")
    required_false = (
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
    )
    if boundaries.get("public_pages_only") is not True:
        raise ValueError("public_pages_only must be true")
    for key in required_false:
        if boundaries.get(key) is not False:
            raise ValueError(f"{key} must be false")

    allowed_paths = contract.get("allowed_paths")
    if not isinstance(allowed_paths, list) or not allowed_paths:
        raise ValueError("allowed_paths must be a non-empty list")
    allowed_path_set = set(allowed_paths)

    targets = contract.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 12:
        raise ValueError("targets must contain between 1 and 12 entries")
    seen_slugs: set[str] = set()
    seen_assertions: set[str] = set()

    for item in targets:
        if not isinstance(item, dict):
            raise ValueError("Each target must be an object")
        slug = item.get("slug")
        url = item.get("url")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            raise ValueError(f"Unsafe target slug: {slug!r}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate target slug: {slug}")
        seen_slugs.add(slug)
        if not isinstance(url, str):
            raise ValueError(f"Missing URL for {slug}")
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.hostname or ''}"
        if (
            parsed.scheme != "https"
            or origin != allowed_origin
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"Target is outside the bounded HTTPS origin: {url}")
        if (parsed.path or "/") not in allowed_path_set:
            raise ValueError(f"Target path is outside allowed_paths: {url}")

        assertions = item.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise ValueError(f"Target {slug} must define assertions")
        for assertion in assertions:
            if not isinstance(assertion, dict):
                raise ValueError(f"Invalid assertion in {slug}")
            assertion_id = assertion.get("id")
            if not isinstance(assertion_id, str) or not assertion_id:
                raise ValueError(f"Assertion in {slug} has no id")
            ref = f"{slug}:{assertion_id}"
            if ref in seen_assertions:
                raise ValueError(f"Duplicate assertion ref: {ref}")
            seen_assertions.add(ref)
            assertion_type = assertion.get("type")
            if assertion_type in {"all_of", "any_of"}:
                markers = assertion.get("markers")
                if not isinstance(markers, list) or not markers or not all(
                    isinstance(marker, str) and marker for marker in markers
                ):
                    raise ValueError(f"Invalid markers for {ref}")
            elif assertion_type == "occurrence":
                marker = assertion.get("marker")
                minimum = assertion.get("min_occurrences")
                if (
                    not isinstance(marker, str)
                    or not marker
                    or not isinstance(minimum, int)
                    or minimum < 1
                ):
                    raise ValueError(f"Invalid occurrence assertion for {ref}")
            else:
                raise ValueError(f"Unsupported assertion type for {ref}: {assertion_type}")

    findings = contract.get("findings")
    if not isinstance(findings, list) or not findings:
        raise ValueError("findings must be a non-empty list")
    finding_ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("Each finding must be an object")
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not re.fullmatch(r"DCL-\d{3}", finding_id):
            raise ValueError(f"Invalid finding id: {finding_id}")
        if finding_id in finding_ids:
            raise ValueError(f"Duplicate finding id: {finding_id}")
        finding_ids.add(finding_id)
        refs = finding.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"{finding_id} must have evidence_refs")
        missing = [ref for ref in refs if ref not in seen_assertions]
        if missing:
            raise ValueError(f"{finding_id} references unknown assertions: {missing}")


def evaluate_assertion(assertion: dict[str, Any], text: str) -> dict[str, Any]:
    case_sensitive = bool(assertion.get("case_sensitive", False))
    haystack = text if case_sensitive else text.casefold()

    assertion_type = assertion["type"]
    result: dict[str, Any] = {
        "id": assertion["id"],
        "type": assertion_type,
        "passed": False,
    }

    if assertion_type in {"all_of", "any_of"}:
        markers = assertion["markers"]
        checks = []
        for marker in markers:
            needle = marker if case_sensitive else marker.casefold()
            checks.append({"marker": marker, "present": needle in haystack})
        result["markers"] = checks
        if assertion_type == "all_of":
            result["passed"] = all(item["present"] for item in checks)
        else:
            result["passed"] = any(item["present"] for item in checks)
        return result

    marker = assertion["marker"]
    needle = marker if case_sensitive else marker.casefold()
    count = haystack.count(needle)
    result.update(
        {
            "marker": marker,
            "observed_occurrences": count,
            "min_occurrences": assertion["min_occurrences"],
            "passed": count >= assertion["min_occurrences"],
        }
    )
    return result


def fetch_target(
    opener: Any,
    item: dict[str, Any],
    timeout_seconds: int,
    max_response_bytes: int,
    user_agent: str,
) -> dict[str, Any]:
    url = item["url"]
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru,en;q=0.8",
        },
        method="GET",
    )
    observed_at = datetime.now(timezone.utc).isoformat()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read(max_response_bytes + 1)
            if len(body) > max_response_bytes:
                raise ValueError(f"Response exceeds {max_response_bytes} bytes")
            charset = response.headers.get_content_charset() or "utf-8"
            decoded = body.decode(charset, errors="replace")
            text = normalize_text(decoded)
            assertions = [
                evaluate_assertion(assertion, text)
                for assertion in item["assertions"]
            ]
            return {
                "slug": item["slug"],
                "url": url,
                "role": item.get("role"),
                "observed_at": observed_at,
                "status": getattr(response, "status", None),
                "final_url": response.geturl(),
                "content_type": response.headers.get("Content-Type"),
                "body_bytes": len(body),
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "assertions": assertions,
                "all_assertions_passed": all(entry["passed"] for entry in assertions),
                "error": None,
            }
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return {
            "slug": item["slug"],
            "url": url,
            "role": item.get("role"),
            "observed_at": observed_at,
            "status": getattr(exc, "code", None),
            "final_url": None,
            "content_type": None,
            "body_bytes": 0,
            "body_sha256": None,
            "assertions": [],
            "all_assertions_passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_finding_results(
    contract: dict[str, Any],
    assertion_index: dict[str, bool],
) -> list[dict[str, Any]]:
    results = []
    for finding in contract["findings"]:
        refs = finding["evidence_refs"]
        passed_refs = [ref for ref in refs if assertion_index.get(ref) is True]
        reproduced = len(passed_refs) == len(refs)
        state = finding["initial_state"] if reproduced else "NEEDS_EVIDENCE"
        results.append(
            {
                "id": finding["id"],
                "title": finding["title"],
                "severity": finding["severity"],
                "state": state,
                "reproduced": reproduced,
                "evidence_refs": refs,
                "passed_evidence_refs": passed_refs,
                "quality_lens": finding["quality_lens"],
                "system_lens": finding["system_lens"],
                "business_lens": finding["business_lens"],
                "promotion_rule": finding["promotion_rule"],
            }
        )
    return results


def render_summary(packet: dict[str, Any]) -> str:
    lines = [
        "# LiminalQA · DCloud outside-in audit v0.1",
        "",
        f"**Decision:** `{packet['decision']}`  ",
        f"**Targets completed:** `{packet['completed_targets']}/{packet['target_count']}`  ",
        f"**Product signals reproduced:** `{packet['reproduced_findings']}/{packet['finding_count']}`",
        "",
        "## Finding matrix",
        "",
        "| ID | Severity | State | Title |",
        "|---|---|---|---|",
    ]
    for finding in packet["findings"]:
        lines.append(
            f"| {finding['id']} | {finding['severity']} | {finding['state']} | "
            f"{finding['title']} |"
        )

    lines.extend(["", "## Target evidence", ""])
    for target in packet["targets"]:
        status = target.get("status")
        error = f" — {target['error']}" if target.get("error") else ""
        lines.append(
            f"- **{target['slug']}**: HTTP `{status}`, assertions "
            f"`{sum(1 for item in target['assertions'] if item['passed'])}/"
            f"{len(target['assertions'])}`{error}"
        )

    lines.extend(
        [
            "",
            "## Authority boundary",
            "",
            "> Evidence only. No authentication, form submission, email, direct API testing,",
            "> active security testing, external reporting, deployment, or merge is authorized.",
            "",
            "A reproduced marker set is a `PRODUCT_SIGNAL`, not a final root-cause claim.",
            "Desktop and mobile rendered evidence plus human review are required for promotion.",
            "",
        ]
    )
    return "\n".join(lines)


def run(contract_path: Path, output_dir: Path) -> int:
    contract = load_json(contract_path)
    validate_contract(contract)

    runtime = contract.get("runtime", {})
    timeout_seconds = int(runtime.get("timeout_seconds", 30))
    max_response_bytes = int(runtime.get("max_response_bytes", 3_000_000))
    user_agent = str(runtime.get("user_agent", "LiminalQA-Passive-Public-Audit/0.1"))
    allowed_origin = contract["target"]["canonical_origin"]
    opener = build_opener(BoundedRedirectHandler(allowed_origin))

    target_results = [
        fetch_target(
            opener,
            item,
            timeout_seconds,
            max_response_bytes,
            user_agent,
        )
        for item in contract["targets"]
    ]

    assertion_index: dict[str, bool] = {}
    for target in target_results:
        for assertion in target["assertions"]:
            assertion_index[f"{target['slug']}:{assertion['id']}"] = bool(assertion["passed"])

    finding_results = build_finding_results(contract, assertion_index)
    completed_targets = sum(1 for target in target_results if target["error"] is None)
    reproduced_findings = sum(1 for finding in finding_results if finding["reproduced"])

    if completed_targets != len(target_results):
        decision = "NEEDS_EVIDENCE"
    elif reproduced_findings:
        decision = "PRODUCT_SIGNAL"
    else:
        decision = "NO_SIGNAL_OBSERVED"

    packet = {
        "schema_version": "liminalqa-tri-lens-public-audit-result-v1",
        "audit_id": contract["audit_id"],
        "target": contract["target"],
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "target_count": len(target_results),
        "completed_targets": completed_targets,
        "finding_count": len(finding_results),
        "reproduced_findings": reproduced_findings,
        "targets": target_results,
        "findings": finding_results,
        "lotus_policy": contract["lotus_policy"],
        "boundaries": contract["boundaries"],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    summary_path = output_dir / "summary.md"
    result_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(render_summary(packet), encoding="utf-8")
    print(render_summary(packet))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        default="audits/dcloud/public-audit-v0.1/contract.json",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/dcloud/public-audit-v0.1",
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    contract_path = Path(args.contract)
    try:
        contract = load_json(contract_path)
        validate_contract(contract)
        if args.validate_only:
            print(f"Validated {contract_path}")
            return 0
        return run(contract_path, Path(args.output_dir))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
