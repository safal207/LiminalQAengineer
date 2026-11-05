#!/usr/bin/env python3
"""Bounded passive public-content probe for the Hi, Rockits! outside-in audit."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SCHEMA = "liminalqa-hi-rockits-public-audit-v1"
RESULT_SCHEMA = "liminalqa-hi-rockits-public-audit-result-v1"
DEFAULT_CONTRACT = Path("audits/hi-rockits/public-audit-v0.1/contract.json")


class VisibleTextParser(HTMLParser):
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
    return f"{parsed.scheme}://{parsed.hostname}"


class BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origins: set[str]) -> None:
        super().__init__()
        self.allowed_origins = allowed_origins

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> urllib.request.Request | None:
        resolved = urllib.parse.urljoin(req.full_url, newurl)
        if canonical_origin(resolved) not in self.allowed_origins:
            raise urllib.error.HTTPError(resolved, code, f"Redirect outside bounded origins: {resolved}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != SCHEMA:
        raise ValueError(f"Unsupported schema: {contract.get('schema_version')!r}")
    origins = set((contract.get("target") or {}).get("canonical_origins") or [])
    expected = {"https://rockits.ru", "https://hirockits.com"}
    if origins != expected:
        raise ValueError(f"Canonical origins must be exactly {sorted(expected)}")

    boundaries = contract.get("boundaries") or {}
    for key in ["public_pages_only", "natural_get_navigation_only"]:
        if boundaries.get(key) is not True:
            raise ValueError(f"Boundary {key} must be true")
    for key in [
        "authentication", "form_submission", "button_clicks", "resume_upload",
        "email_or_external_contact", "direct_api_testing", "active_security_testing",
        "enumeration", "fuzzing", "load_testing", "vulnerability_claim",
        "external_submission_authorized", "deployment_authorized", "merge_authorized",
    ]:
        if boundaries.get(key) is not False:
            raise ValueError(f"Boundary {key} must be false")

    runtime = contract.get("runtime") or {}
    if runtime.get("max_parallel") != 1:
        raise ValueError("The audit must remain sequential")
    allowed_paths = contract.get("allowed_paths") or {}
    targets = contract.get("targets") or []
    if len(targets) != 4:
        raise ValueError("Target count must be exactly 4")

    refs: set[str] = set()
    for target in targets:
        raw_url = target.get("url")
        parsed = urllib.parse.urlsplit(raw_url)
        origin = canonical_origin(raw_url)
        if parsed.scheme != "https" or origin not in origins:
            raise ValueError(f"Target outside bounded HTTPS origins: {raw_url}")
        if parsed.query or parsed.fragment:
            raise ValueError(f"Target must not include query or fragment: {raw_url}")
        if (parsed.path or "/") not in set(allowed_paths.get(origin) or []):
            raise ValueError(f"Target path is not allowlisted: {raw_url}")
        for assertion in target.get("assertions") or []:
            ref = f"{target['slug']}:{assertion.get('id')}"
            if ref in refs:
                raise ValueError(f"Duplicate assertion ref: {ref}")
            refs.add(ref)
            if assertion.get("type") not in {"all_of", "any_of", "occurrence"}:
                raise ValueError(f"Unsupported assertion type: {ref}")

    for finding in contract.get("findings") or []:
        evidence_refs = finding.get("evidence_refs") or []
        if not evidence_refs or any(ref not in refs for ref in evidence_refs):
            raise ValueError(f"Finding has invalid evidence refs: {finding.get('id')}")


def extract_visible_text(raw_html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(raw_html)
    parser.close()
    return normalize_text(" ".join(parser.parts))


def marker_context(text: str, marker: str, radius: int = 150) -> str | None:
    idx = text.casefold().find(marker.casefold())
    if idx < 0:
        return None
    return text[max(0, idx - radius): min(len(text), idx + len(marker) + radius)]


def evaluate_assertion(assertion: dict[str, Any], text: str) -> dict[str, Any]:
    corpus = text if assertion.get("case_sensitive") else text.casefold()
    if assertion["type"] in {"all_of", "any_of"}:
        items = []
        for marker in assertion["markers"]:
            needle = marker if assertion.get("case_sensitive") else marker.casefold()
            items.append({"marker": marker, "present": needle in corpus, "context": marker_context(text, marker)})
        passed = all(item["present"] for item in items) if assertion["type"] == "all_of" else any(item["present"] for item in items)
        return {"id": assertion["id"], "type": assertion["type"], "passed": passed, "markers": items}
    marker = assertion["marker"]
    needle = marker if assertion.get("case_sensitive") else marker.casefold()
    count = corpus.count(needle)
    return {
        "id": assertion["id"], "type": "occurrence", "marker": marker,
        "observed_occurrences": count, "min_occurrences": assertion["min_occurrences"],
        "passed": count >= assertion["min_occurrences"], "context": marker_context(text, marker),
    }


def observe(contract: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    allowed_origins = set(contract["target"]["canonical_origins"])
    runtime = contract["runtime"]
    opener = urllib.request.build_opener(BoundedRedirectHandler(allowed_origins))
    request = urllib.request.Request(target["url"], headers={
        "User-Agent": runtime["user_agent"],
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    })
    try:
        with opener.open(request, timeout=runtime["timeout_seconds"]) as response:
            final_url = response.geturl()
            body = response.read(runtime["max_response_bytes"] + 1)
            if len(body) > runtime["max_response_bytes"]:
                raise ValueError("Response exceeded max_response_bytes")
            content_type = response.headers.get("Content-Type", "")
            charset_match = re.search(r"charset=([\w.-]+)", content_type, re.I)
            charset = charset_match.group(1) if charset_match else "utf-8"
            raw_html = body.decode(charset, errors="replace")
            text = extract_visible_text(raw_html)
            return {
                "slug": target["slug"], "requested_url": target["url"], "final_url": final_url,
                "status": getattr(response, "status", None), "error": None,
                "origin_stayed_bounded": canonical_origin(final_url) in allowed_origins,
                "response_bytes": len(body), "body_sha256": sha256_bytes(body),
                "visible_text_sha256": sha256_bytes(text.encode()), "visible_text_length": len(text),
                "visible_text_sample": text[:5000],
                "assertions": [evaluate_assertion(a, text) for a in target["assertions"]],
            }
    except Exception as exc:  # bounded failure is evidence, not a crash
        return {
            "slug": target["slug"], "requested_url": target["url"],
            "final_url": getattr(exc, "url", None), "status": getattr(exc, "code", None),
            "error": str(exc), "origin_stayed_bounded": False, "response_bytes": 0,
            "body_sha256": None, "visible_text_sha256": None, "visible_text_length": 0,
            "visible_text_sample": "", "assertions": [
                {"id": a["id"], "type": a["type"], "passed": False, "error": "target_observation_failed"}
                for a in target["assertions"]
            ],
        }


def aggregate(contract: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    assertion_map = {
        f"{obs['slug']}:{a['id']}": a for obs in observations for a in obs["assertions"]
    }
    findings = []
    for finding in contract["findings"]:
        refs = finding["evidence_refs"]
        passed = all(assertion_map.get(ref, {}).get("passed") is True for ref in refs)
        findings.append({
            "id": finding["id"], "title": finding["title"], "severity": finding["severity"],
            "state": "PRODUCT_SIGNAL" if passed else "NEEDS_EVIDENCE",
            "evidence_refs": refs, "root_cause": "HYPOTHESIS_ONLY",
            "business_impact": "PLAUSIBLE_NOT_MEASURED",
        })
    return {
        "expected_target_count": len(contract["targets"]),
        "observed_target_count": len(observations),
        "successful_http_2xx": sum(1 for o in observations if isinstance(o.get("status"), int) and 200 <= o["status"] < 300),
        "bounded_observations": sum(1 for o in observations if o.get("origin_stayed_bounded")),
        "findings": findings,
        "decision": "PRODUCT_SIGNALS" if any(f["state"] == "PRODUCT_SIGNAL" for f in findings) else "NEEDS_EVIDENCE",
    }


def render_summary(result: dict[str, Any]) -> str:
    lines = ["# Hi, Rockits! outside-in audit v0.1", "", f"Generated: `{result['generated_at']}`", ""]
    agg = result["aggregate"]
    lines += [f"- Targets: `{agg['observed_target_count']}/{agg['expected_target_count']}`", f"- HTTP 2xx: `{agg['successful_http_2xx']}`", f"- Decision: `{agg['decision']}`", "", "## Findings", ""]
    for finding in agg["findings"]:
        lines.append(f"- `{finding['id']}` · **{finding['severity']}** · `{finding['state']}` — {finding['title']}")
    lines += ["", "## Authority", "", "Evidence only. External submission, deployment, and merge remain blocked.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/hi-rockits/public-audit-v0.1"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    contract = load_json(args.contract)
    validate_contract(contract)
    if args.validate_only:
        return 0
    observations = [observe(contract, target) for target in contract["targets"]]
    result = {
        "schema_version": RESULT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_id": contract["audit_id"], "target": contract["target"],
        "boundaries": contract["boundaries"], "observations": observations,
        "aggregate": aggregate(contract, observations),
        "authority": {"mode": "evidence_only", "grants": {"external_submission": False, "deployment": False, "merge": False}},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "summary.md").write_text(render_summary(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
