#!/usr/bin/env python3
"""Deterministic, network-free replays for security lifecycle guardrails.

The vulnerable models intentionally encode mechanisms observed in historical code.
The guarded models encode the smallest corrective invariant. This module never
connects to Tradernet, Redis, WebSocket servers, accounts, or order endpoints.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


SCHEMA_VERSION = "0.2"
AUTHORITY = "LOCAL_DETERMINISTIC_SIMULATION_ONLY"
EXTERNAL_PRODUCT_CLAIM = "NONE"


@dataclass(frozen=True, slots=True)
class ConnectionRef:
    user_id: str
    ws_id: str
    generation: int

    @property
    def membership_token(self) -> str:
        return f"{self.user_id}:{self.ws_id}:{self.generation}"


class VulnerableRedisMembership:
    """Models SADD(user_id) followed by SREM(ws_id)."""

    def __init__(self) -> None:
        self.channels: dict[str, set[str]] = {}

    def subscribe(self, connection: ConnectionRef, channel: str) -> None:
        self.channels.setdefault(channel, set()).add(connection.user_id)

    def unsubscribe(self, connection: ConnectionRef, channel: str) -> None:
        self.channels.setdefault(channel, set()).discard(connection.ws_id)

    def members(self, channel: str) -> set[str]:
        return set(self.channels.get(channel, set()))


class GuardedRedisMembership:
    """Adds and removes the exact same generation-scoped identity."""

    def __init__(self) -> None:
        self.channels: dict[str, set[str]] = {}

    def subscribe(self, connection: ConnectionRef, channel: str) -> None:
        self.channels.setdefault(channel, set()).add(connection.membership_token)

    def unsubscribe(self, connection: ConnectionRef, channel: str) -> None:
        self.channels.setdefault(channel, set()).discard(connection.membership_token)

    def members(self, channel: str) -> set[str]:
        return set(self.channels.get(channel, set()))


class VulnerableMultiSocketManager:
    """Models one-socket disconnect performing user-wide subscription cleanup."""

    def __init__(self) -> None:
        self.connections: dict[str, set[str]] = {}
        self.user_channels: dict[str, set[str]] = {}

    def connect(self, connection: ConnectionRef) -> None:
        self.connections.setdefault(connection.user_id, set()).add(connection.ws_id)

    def subscribe(self, connection: ConnectionRef, channel: str) -> None:
        self.user_channels.setdefault(connection.user_id, set()).add(channel)

    def disconnect(self, connection: ConnectionRef) -> None:
        self.connections.setdefault(connection.user_id, set()).discard(connection.ws_id)
        self.user_channels.pop(connection.user_id, None)

    def receives(self, connection: ConnectionRef, channel: str) -> bool:
        return (
            connection.ws_id in self.connections.get(connection.user_id, set())
            and channel in self.user_channels.get(connection.user_id, set())
        )


class GuardedMultiSocketManager:
    """Owns subscriptions by physical connection and generation."""

    def __init__(self) -> None:
        self.connections: set[ConnectionRef] = set()
        self.connection_channels: dict[ConnectionRef, set[str]] = {}

    def connect(self, connection: ConnectionRef) -> None:
        self.connections.add(connection)

    def subscribe(self, connection: ConnectionRef, channel: str) -> None:
        if connection not in self.connections:
            raise ValueError("connection is not active")
        self.connection_channels.setdefault(connection, set()).add(channel)

    def disconnect(self, connection: ConnectionRef) -> None:
        self.connections.discard(connection)
        self.connection_channels.pop(connection, None)

    def receives(self, connection: ConnectionRef, channel: str) -> bool:
        return (
            connection in self.connections
            and channel in self.connection_channels.get(connection, set())
        )


class VulnerableGenerationState:
    """Models a stale disconnect deleting whichever generation is current."""

    def __init__(self) -> None:
        self.current: dict[str, int] = {}
        self.subscribed: set[tuple[str, int]] = set()

    def connect_and_subscribe(self, connection: ConnectionRef) -> None:
        self.current[connection.user_id] = connection.generation
        self.subscribed.add((connection.user_id, connection.generation))

    def disconnect(self, connection: ConnectionRef) -> None:
        self.current.pop(connection.user_id, None)
        self.subscribed = {
            item for item in self.subscribed if item[0] != connection.user_id
        }

    def is_current_and_subscribed(self, connection: ConnectionRef) -> bool:
        return (
            self.current.get(connection.user_id) == connection.generation
            and (connection.user_id, connection.generation) in self.subscribed
        )


class GuardedGenerationState:
    """Rejects cleanup from a stale generation."""

    def __init__(self) -> None:
        self.current: dict[str, int] = {}
        self.subscribed: set[tuple[str, int]] = set()

    def connect_and_subscribe(self, connection: ConnectionRef) -> None:
        self.current[connection.user_id] = connection.generation
        self.subscribed.add((connection.user_id, connection.generation))

    def disconnect(self, connection: ConnectionRef) -> None:
        self.subscribed.discard((connection.user_id, connection.generation))
        if self.current.get(connection.user_id) == connection.generation:
            self.current.pop(connection.user_id, None)

    def is_current_and_subscribed(self, connection: ConnectionRef) -> bool:
        return (
            self.current.get(connection.user_id) == connection.generation
            and (connection.user_id, connection.generation) in self.subscribed
        )


class VulnerableSelfEchoBus:
    """Models local delivery followed by processing the publisher's Pub/Sub echo."""

    def deliver(self, socket_ids: Iterable[str], event_id: str) -> dict[str, int]:
        counts = {socket_id: 0 for socket_id in socket_ids}
        for socket_id in counts:
            counts[socket_id] += 1  # immediate local delivery
        for socket_id in counts:
            counts[socket_id] += 1  # same-instance Pub/Sub echo
        return counts


class GuardedSelfEchoBus:
    """Suppresses the publishing instance and deduplicates by event ID."""

    def __init__(self) -> None:
        self.seen: dict[str, set[str]] = {}

    def _deliver_once(self, socket_id: str, event_id: str, counts: dict[str, int]) -> None:
        seen = self.seen.setdefault(socket_id, set())
        if event_id in seen:
            return
        seen.add(event_id)
        counts[socket_id] += 1

    def deliver(self, socket_ids: Iterable[str], event_id: str) -> dict[str, int]:
        counts = {socket_id: 0 for socket_id in socket_ids}
        for socket_id in counts:
            self._deliver_once(socket_id, event_id, counts)
        # A same-instance echo is harmless because event_id is already seen.
        for socket_id in counts:
            self._deliver_once(socket_id, event_id, counts)
        return counts


@dataclass(frozen=True, slots=True)
class MutationContext:
    environment: str
    origin: str
    account_mode: str
    mutation_enabled: bool
    nonce: str
    confirmation: str


class MutationRefused(RuntimeError):
    pass


class FinancialMutationGate:
    """Authorizes a simulated mutation but never performs an external action."""

    ALLOWED_ENVIRONMENTS = frozenset({"test", "sandbox"})
    ALLOWED_ORIGINS = frozenset(
        {
            "https://tradernet-sandbox.example",
            "https://tradernet-test.example",
        }
    )

    def __init__(self) -> None:
        self.used_nonces: set[str] = set()

    @staticmethod
    def _canonical_origin(origin: str) -> str:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc:
            raise MutationRefused("origin must be an exact HTTPS origin")
        if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
            raise MutationRefused("origin must not contain path, query, or fragment")
        return f"{parsed.scheme}://{parsed.netloc.lower()}"

    def authorize(self, context: MutationContext) -> dict[str, str]:
        if context.environment not in self.ALLOWED_ENVIRONMENTS:
            raise MutationRefused("environment is not non-production")
        origin = self._canonical_origin(context.origin)
        if origin not in self.ALLOWED_ORIGINS:
            raise MutationRefused("origin is not allowlisted")
        if context.account_mode != "sandbox":
            raise MutationRefused("account is not explicitly sandbox-scoped")
        if not context.mutation_enabled:
            raise MutationRefused("explicit mutation flag is missing")
        if not context.nonce or context.nonce in self.used_nonces:
            raise MutationRefused("nonce is missing or already used")
        expected = f"CONFIRM-SANDBOX-MUTATION:{context.nonce}"
        if context.confirmation != expected:
            raise MutationRefused("confirmation does not bind the nonce")
        self.used_nonces.add(context.nonce)
        return {
            "decision": "SIMULATED_MUTATION_AUTHORIZED",
            "origin": origin,
            "authority": AUTHORITY,
        }


SENSITIVE_HEADER_NAMES = frozenset(
    {"authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token"}
)


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: "<redacted>" if name.lower() in SENSITIVE_HEADER_NAMES else value
        for name, value in headers.items()
    }


def redact_text(value: str) -> str:
    patterns = (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
        re.compile(r"(?i)\b(?:sid|session|token)\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}"),
    )
    result = value
    for pattern in patterns:
        result = pattern.sub("<redacted>", result)
    return result


class FakeTransport:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def request(self, *, timeout_seconds: float) -> dict[str, Any]:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout must be positive and finite")
        self.timeouts.append(timeout_seconds)
        return {"status": 200, "simulated": True}


class BoundedHttpClient:
    def __init__(self, transport: FakeTransport, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds > 30:
            raise ValueError("local audit timeout must be at most 30 seconds")
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def get(self) -> dict[str, Any]:
        return self.transport.request(timeout_seconds=self.timeout_seconds)


def render_safe_html_report(title: str, diagnostic: str, environment: str) -> str:
    return (
        "<!doctype html><html><body>"
        f"<h1>{html.escape(title, quote=True)}</h1>"
        f"<pre>{html.escape(diagnostic, quote=True)}</pre>"
        f"<span>{html.escape(environment, quote=True)}</span>"
        "</body></html>"
    )


def classify_evidence(
    *,
    executed: bool,
    passed: bool,
    mocked: bool = False,
    skipped: bool = False,
    available: bool = True,
) -> str:
    if not available:
        return "UNAVAILABLE"
    if skipped or not executed:
        return "NOT_RUN"
    if mocked:
        return "SIMULATED_PASS" if passed else "SIMULATED_FAIL"
    return "LIVE_PASS" if passed else "LIVE_FAIL"


def replay_identity_symmetry() -> dict[str, Any]:
    connection = ConnectionRef("user-1", "ws-1", 1)
    channel = "quotes:AAPL.US"

    vulnerable = VulnerableRedisMembership()
    vulnerable.subscribe(connection, channel)
    vulnerable.unsubscribe(connection, channel)

    guarded = GuardedRedisMembership()
    guarded.subscribe(connection, channel)
    guarded.unsubscribe(connection, channel)

    return {
        "scenario_id": "CCG-REDIS-IDENTITY-SYMMETRY",
        "vulnerable": {
            "remaining_members": sorted(vulnerable.members(channel)),
            "invariant_pass": not vulnerable.members(channel),
        },
        "guarded": {
            "remaining_members": sorted(guarded.members(channel)),
            "invariant_pass": not guarded.members(channel),
        },
        "claim": "LOCAL_MECHANISM_REPRODUCED",
    }


def replay_two_socket_cleanup() -> dict[str, Any]:
    first = ConnectionRef("user-1", "ws-old", 1)
    second = ConnectionRef("user-1", "ws-new", 2)
    channel = "quotes:MSFT.US"

    vulnerable = VulnerableMultiSocketManager()
    for connection in (first, second):
        vulnerable.connect(connection)
        vulnerable.subscribe(connection, channel)
    vulnerable.disconnect(first)

    guarded = GuardedMultiSocketManager()
    for connection in (first, second):
        guarded.connect(connection)
        guarded.subscribe(connection, channel)
    guarded.disconnect(first)

    return {
        "scenario_id": "CCG-WS-TWO-SOCKET-CLEANUP",
        "vulnerable": {
            "survivor_receives": vulnerable.receives(second, channel),
            "invariant_pass": vulnerable.receives(second, channel),
        },
        "guarded": {
            "survivor_receives": guarded.receives(second, channel),
            "invariant_pass": guarded.receives(second, channel),
        },
        "claim": "LOCAL_MECHANISM_REPRODUCED",
    }


def replay_generation_fence() -> dict[str, Any]:
    old = ConnectionRef("user-1", "ws-old", 1)
    new = ConnectionRef("user-1", "ws-new", 2)

    vulnerable = VulnerableGenerationState()
    vulnerable.connect_and_subscribe(old)
    vulnerable.connect_and_subscribe(new)
    vulnerable.disconnect(old)

    guarded = GuardedGenerationState()
    guarded.connect_and_subscribe(old)
    guarded.connect_and_subscribe(new)
    guarded.disconnect(old)

    return {
        "scenario_id": "CCG-WS-GENERATION-FENCE",
        "vulnerable": {
            "new_generation_survives": vulnerable.is_current_and_subscribed(new),
            "invariant_pass": vulnerable.is_current_and_subscribed(new),
        },
        "guarded": {
            "new_generation_survives": guarded.is_current_and_subscribed(new),
            "invariant_pass": guarded.is_current_and_subscribed(new),
        },
        "claim": "LOCAL_MECHANISM_REPRODUCED",
    }


def replay_self_echo() -> dict[str, Any]:
    sockets = ("ws-a", "ws-b")
    event_id = "event-0001"
    vulnerable_counts = VulnerableSelfEchoBus().deliver(sockets, event_id)
    guarded_counts = GuardedSelfEchoBus().deliver(sockets, event_id)

    return {
        "scenario_id": "CCG-REDIS-SELF-ECHO",
        "vulnerable": {
            "delivery_counts": vulnerable_counts,
            "invariant_pass": all(value == 1 for value in vulnerable_counts.values()),
        },
        "guarded": {
            "delivery_counts": guarded_counts,
            "invariant_pass": all(value == 1 for value in guarded_counts.values()),
        },
        "claim": "LOCAL_MECHANISM_REPRODUCED",
    }


def replay_mutation_gate() -> dict[str, Any]:
    gate = FinancialMutationGate()
    rejected: dict[str, str] = {}

    cases = {
        "production_environment": MutationContext(
            "production",
            "https://tradernet-sandbox.example",
            "sandbox",
            True,
            "nonce-production",
            "CONFIRM-SANDBOX-MUTATION:nonce-production",
        ),
        "unlisted_origin": MutationContext(
            "sandbox",
            "https://tradernet.example",
            "sandbox",
            True,
            "nonce-origin",
            "CONFIRM-SANDBOX-MUTATION:nonce-origin",
        ),
        "non_sandbox_account": MutationContext(
            "sandbox",
            "https://tradernet-sandbox.example",
            "live",
            True,
            "nonce-account",
            "CONFIRM-SANDBOX-MUTATION:nonce-account",
        ),
        "missing_flag": MutationContext(
            "sandbox",
            "https://tradernet-sandbox.example",
            "sandbox",
            False,
            "nonce-flag",
            "CONFIRM-SANDBOX-MUTATION:nonce-flag",
        ),
    }
    for name, context in cases.items():
        try:
            gate.authorize(context)
        except MutationRefused as exc:
            rejected[name] = str(exc)
        else:  # pragma: no cover - this path is itself a safety failure
            rejected[name] = "UNEXPECTEDLY_AUTHORIZED"

    allowed = MutationContext(
        "sandbox",
        "https://tradernet-sandbox.example",
        "sandbox",
        True,
        "nonce-allowed",
        "CONFIRM-SANDBOX-MUTATION:nonce-allowed",
    )
    decision = gate.authorize(allowed)
    replay_refused = False
    try:
        gate.authorize(allowed)
    except MutationRefused:
        replay_refused = True

    invariant_pass = (
        len(rejected) == len(cases)
        and all(value != "UNEXPECTEDLY_AUTHORIZED" for value in rejected.values())
        and decision["decision"] == "SIMULATED_MUTATION_AUTHORIZED"
        and replay_refused
    )
    return {
        "scenario_id": "CCG-FINANCIAL-MUTATION-GATE",
        "guarded": {
            "rejected_cases": rejected,
            "allowed_decision": decision,
            "replayed_nonce_refused": replay_refused,
            "invariant_pass": invariant_pass,
        },
        "claim": "LOCAL_GUARDRAIL_VALIDATED",
    }


def replay_secret_redaction() -> dict[str, Any]:
    secret_cookie = "session-super-secret-1234567890"
    secret_bearer = "Bearer bearer-super-secret-0987654321"
    headers = redact_headers(
        {
            "Cookie": secret_cookie,
            "Authorization": secret_bearer,
            "Accept": "application/json",
        }
    )
    diagnostic = redact_text(
        f"failure sid={secret_cookie} authorization={secret_bearer}"
    )
    serialized = json.dumps(
        {"headers": headers, "diagnostic": diagnostic}, sort_keys=True
    )
    invariant_pass = secret_cookie not in serialized and secret_bearer not in serialized
    return {
        "scenario_id": "CCG-SECRET-REDACTION",
        "guarded": {
            "headers": headers,
            "diagnostic": diagnostic,
            "invariant_pass": invariant_pass,
        },
        "claim": "LOCAL_GUARDRAIL_VALIDATED",
    }


def replay_timeout_and_html() -> dict[str, Any]:
    transport = FakeTransport()
    response = BoundedHttpClient(transport, timeout_seconds=5.0).get()
    hostile = '<script data-test="sentinel">alert(1)</script>'
    report = render_safe_html_report(hostile, hostile, hostile)
    invariant_pass = (
        response == {"status": 200, "simulated": True}
        and transport.timeouts == [5.0]
        and hostile not in report
        and "&lt;script" in report
    )
    return {
        "scenario_id": "CCG-BOUNDED-IO-AND-HTML",
        "guarded": {
            "request_timeouts": transport.timeouts,
            "raw_script_present": hostile in report,
            "escaped_script_present": "&lt;script" in report,
            "invariant_pass": invariant_pass,
        },
        "claim": "LOCAL_GUARDRAIL_VALIDATED",
    }


def replay_evidence_classes() -> dict[str, Any]:
    classifications = {
        "mock_pass": classify_evidence(executed=True, passed=True, mocked=True),
        "skipped": classify_evidence(executed=False, passed=False, skipped=True),
        "unavailable": classify_evidence(
            executed=False, passed=False, available=False
        ),
        "live_pass": classify_evidence(executed=True, passed=True),
    }
    invariant_pass = classifications == {
        "mock_pass": "SIMULATED_PASS",
        "skipped": "NOT_RUN",
        "unavailable": "UNAVAILABLE",
        "live_pass": "LIVE_PASS",
    }
    return {
        "scenario_id": "CCG-EVIDENCE-CLASS-SEPARATION",
        "guarded": {
            "classifications": classifications,
            "invariant_pass": invariant_pass,
        },
        "claim": "LOCAL_GUARDRAIL_VALIDATED",
    }


def build_replay_result(source_sha: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source_sha must be an exact lowercase 40-character SHA")

    scenarios = [
        replay_identity_symmetry(),
        replay_two_socket_cleanup(),
        replay_generation_fence(),
        replay_self_echo(),
        replay_mutation_gate(),
        replay_secret_redaction(),
        replay_timeout_and_html(),
        replay_evidence_classes(),
    ]

    mechanism_scenarios = [
        scenario for scenario in scenarios if "vulnerable" in scenario
    ]
    mechanisms_reproduced = all(
        not scenario["vulnerable"]["invariant_pass"]
        and scenario["guarded"]["invariant_pass"]
        for scenario in mechanism_scenarios
    )
    all_guardrails_pass = all(
        scenario["guarded"]["invariant_pass"] for scenario in scenarios
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_sha": source_sha,
        "authority": AUTHORITY,
        "network_access": False,
        "credential_use": False,
        "external_mutation": False,
        "external_product_claim": EXTERNAL_PRODUCT_CLAIM,
        "scenario_count": len(scenarios),
        "mechanism_scenario_count": len(mechanism_scenarios),
        "mechanisms_reproduced": mechanisms_reproduced,
        "all_guardrails_pass": all_guardrails_pass,
        "verdict": (
            "CONFIRMED_LOCAL_MECHANISM_REPRODUCTION_AND_GUARDRAIL_PASS"
            if mechanisms_reproduced and all_guardrails_pass
            else "LOCAL_REPLAY_FAILED"
        ),
        "scenarios": scenarios,
        "non_claims": [
            "No Tradernet internal implementation is inferred.",
            "No server-side Redis leak is confirmed.",
            "No authenticated account behavior is tested.",
            "No order, cancellation, portfolio, or financial operation is performed.",
        ],
    }


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_replay_result(args.source_sha)
    rendered = canonical_json_bytes(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered)
    else:
        print(rendered.decode("utf-8"), end="")
    return 0 if payload["verdict"].startswith("CONFIRMED_LOCAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
