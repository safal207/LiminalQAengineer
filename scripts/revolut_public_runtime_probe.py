#!/usr/bin/env python3
"""Probe two documented Revolut X public endpoints without authentication.

The probe is deliberately low impact: exactly one GET per endpoint, at least
1.1 seconds apart, no cookies, no credentials, and no raw response payloads in
the generated artifact. Only status, schema shape, counts, and SHA-256 digests
are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "liminalqa-revolut-public-runtime-probe-v0.1"
USER_AGENT = "LiminalQA-Public-Audit/1.0"
SPACING_SECONDS = 1.1
MAX_BODY_BYTES = 2_000_000
ENDPOINTS = (
    (
        "last_trades",
        "https://revx.revolut.com/api/1.0/public/last-trades",
    ),
    (
        "order_book_btc_usd",
        "https://revx.revolut.com/api/1.0/public/order-book/BTC-USD",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def sorted_keys(value: Any) -> list[str]:
    return sorted(str(key) for key in value) if isinstance(value, dict) else []


def decimal_prices(levels: Any) -> list[Decimal] | None:
    if not isinstance(levels, list):
        return None
    prices: list[Decimal] = []
    for level in levels:
        if not isinstance(level, dict) or not isinstance(level.get("p"), str):
            return None
        try:
            prices.append(Decimal(level["p"]))
        except InvalidOperation:
            return None
    return prices


def is_descending(values: list[Decimal] | None) -> bool | None:
    if values is None:
        return None
    return all(left >= right for left, right in zip(values, values[1:]))


def summarize_json(kind: str, payload: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "top_level_type": json_type(payload),
        "top_level_keys": sorted_keys(payload),
        "contract_ok": False,
    }
    if not isinstance(payload, dict):
        return summary

    data = payload.get("data")
    metadata = payload.get("metadata")
    summary["metadata_type"] = json_type(metadata)
    summary["metadata_keys"] = sorted_keys(metadata)
    summary["metadata_timestamp_type"] = (
        json_type(metadata.get("timestamp")) if isinstance(metadata, dict) else "missing"
    )

    if kind == "last_trades":
        summary["data_type"] = json_type(data)
        summary["item_count"] = len(data) if isinstance(data, list) else None
        summary["first_item_keys"] = sorted_keys(data[0]) if isinstance(data, list) and data else []
        summary["contract_ok"] = isinstance(data, list) and isinstance(metadata, dict)
        return summary

    if kind == "order_book_btc_usd":
        asks = data.get("asks") if isinstance(data, dict) else None
        bids = data.get("bids") if isinstance(data, dict) else None
        summary.update(
            {
                "data_type": json_type(data),
                "data_keys": sorted_keys(data),
                "ask_count": len(asks) if isinstance(asks, list) else None,
                "bid_count": len(bids) if isinstance(bids, list) else None,
                "first_ask_keys": sorted_keys(asks[0]) if isinstance(asks, list) and asks else [],
                "first_bid_keys": sorted_keys(bids[0]) if isinstance(bids, list) and bids else [],
                "asks_descending": is_descending(decimal_prices(asks)),
                "bids_descending": is_descending(decimal_prices(bids)),
            }
        )
        summary["contract_ok"] = (
            isinstance(data, dict)
            and isinstance(asks, list)
            and isinstance(bids, list)
            and isinstance(metadata, dict)
        )
        return summary

    return summary


def classify(status: int | None, contract_ok: bool) -> str:
    if status == 200 and contract_ok:
        return "PUBLIC_NO_AUTH_CONFIRMED"
    if status in {401, 403}:
        return "AUTH_REQUIRED_AT_RUNTIME"
    if status is None:
        return "NETWORK_UNAVAILABLE"
    return "RUNTIME_RESPONSE_MISMATCH"


def read_limited(response: Any) -> tuple[bytes, bool]:
    body = response.read(MAX_BODY_BYTES + 1)
    truncated = len(body) > MAX_BODY_BYTES
    return body[:MAX_BODY_BYTES], truncated


def content_type(headers: Any) -> str | None:
    if headers is None:
        return None
    getter = getattr(headers, "get_content_type", None)
    if callable(getter):
        return getter()
    value = headers.get("Content-Type") if hasattr(headers, "get") else None
    return value.split(";", 1)[0].strip() if isinstance(value, str) else None


def response_summary(
    kind: str,
    url: str,
    status: int,
    final_url: str,
    headers: Any,
    body: bytes,
    truncated: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": kind,
        "url": url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type(headers),
        "body_bytes": len(body),
        "body_sha256": sha256_bytes(body),
        "body_truncated": truncated,
        "json_parse_ok": False,
    }
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        result["schema"] = {
            "top_level_type": "unparseable",
            "top_level_keys": [],
            "contract_ok": False,
        }
    else:
        result["json_parse_ok"] = True
        result["schema"] = summarize_json(kind, payload)
    result["classification"] = classify(status, bool(result["schema"]["contract_ok"]))
    return result


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


def probe_endpoint(
    kind: str,
    url: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = build_request(url)
    try:
        with opener(request, timeout=20) as response:
            body, truncated = read_limited(response)
            status = int(getattr(response, "status", response.getcode()))
            final_url = str(response.geturl())
            return response_summary(kind, url, status, final_url, response.headers, body, truncated)
    except urllib.error.HTTPError as error:
        body, truncated = read_limited(error)
        return response_summary(
            kind,
            url,
            int(error.code),
            str(error.geturl()),
            error.headers,
            body,
            truncated,
        )
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
        return {
            "kind": kind,
            "url": url,
            "final_url": None,
            "status": None,
            "content_type": None,
            "body_bytes": 0,
            "body_sha256": None,
            "body_truncated": False,
            "json_parse_ok": False,
            "schema": {
                "top_level_type": "unavailable",
                "top_level_keys": [],
                "contract_ok": False,
            },
            "classification": "NETWORK_UNAVAILABLE",
            "network_error_type": type(error).__name__,
        }


def run_probe(sleeper: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for index, (kind, url) in enumerate(ENDPOINTS):
        if index:
            sleeper(SPACING_SECONDS)
        observations.append(probe_endpoint(kind, url))

    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": utc_now(),
        "scope": "two documented Revolut X public market-data endpoints",
        "constraints": {
            "request_count": len(ENDPOINTS),
            "requests_per_endpoint": 1,
            "minimum_spacing_seconds": SPACING_SECONDS,
            "auth_headers_sent": False,
            "cookies_sent": False,
            "request_body_sent": False,
            "raw_response_body_persisted": False,
            "account_access": False,
            "trading_action": False,
        },
        "endpoints": observations,
        "summary": {
            "public_no_auth_confirmed": sum(
                item["classification"] == "PUBLIC_NO_AUTH_CONFIRMED" for item in observations
            ),
            "auth_required_at_runtime": sum(
                item["classification"] == "AUTH_REQUIRED_AT_RUNTIME" for item in observations
            ),
            "network_unavailable": sum(
                item["classification"] == "NETWORK_UNAVAILABLE" for item in observations
            ),
            "runtime_response_mismatch": sum(
                item["classification"] == "RUNTIME_RESPONSE_MISMATCH" for item in observations
            ),
        },
        "limitations": [
            "A successful public response confirms only unauthenticated runtime access and the observed schema at this instant.",
            "A network failure is not evidence that the endpoint is unavailable to normal clients.",
            "No security vulnerability is claimed by this probe.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = run_probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
