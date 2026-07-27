from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "cyber_causal_guardrail_replay.py"
SPEC = importlib.util.spec_from_file_location("cyber_causal_guardrail_replay", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replay
SPEC.loader.exec_module(replay)


SOURCE_SHA = "a" * 40


class CyberCausalGuardrailReplayTests(unittest.TestCase):
    def test_identity_mismatch_reproduces_zombie_membership_mechanism(self) -> None:
        result = replay.replay_identity_symmetry()
        self.assertFalse(result["vulnerable"]["invariant_pass"])
        self.assertEqual(["user-1"], result["vulnerable"]["remaining_members"])
        self.assertTrue(result["guarded"]["invariant_pass"])
        self.assertEqual([], result["guarded"]["remaining_members"])

    def test_closing_one_socket_does_not_remove_survivor_subscription(self) -> None:
        result = replay.replay_two_socket_cleanup()
        self.assertFalse(result["vulnerable"]["survivor_receives"])
        self.assertTrue(result["guarded"]["survivor_receives"])

    def test_stale_generation_cleanup_cannot_delete_current_generation(self) -> None:
        result = replay.replay_generation_fence()
        self.assertFalse(result["vulnerable"]["new_generation_survives"])
        self.assertTrue(result["guarded"]["new_generation_survives"])

    def test_pubsub_self_echo_is_deduplicated_per_socket(self) -> None:
        result = replay.replay_self_echo()
        self.assertEqual(
            {"ws-a": 2, "ws-b": 2},
            result["vulnerable"]["delivery_counts"],
        )
        self.assertEqual(
            {"ws-a": 1, "ws-b": 1},
            result["guarded"]["delivery_counts"],
        )

    def test_financial_mutation_gate_refuses_production_and_ambiguous_context(self) -> None:
        result = replay.replay_mutation_gate()
        rejected = result["guarded"]["rejected_cases"]
        self.assertEqual(
            {
                "production_environment",
                "unlisted_origin",
                "non_sandbox_account",
                "missing_flag",
            },
            set(rejected),
        )
        self.assertNotIn("UNEXPECTEDLY_AUTHORIZED", rejected.values())
        self.assertTrue(result["guarded"]["invariant_pass"])

    def test_financial_mutation_gate_binds_confirmation_and_nonce_once(self) -> None:
        gate = replay.FinancialMutationGate()
        context = replay.MutationContext(
            environment="sandbox",
            origin="https://tradernet-sandbox.example",
            account_mode="sandbox",
            mutation_enabled=True,
            nonce="one-use",
            confirmation="CONFIRM-SANDBOX-MUTATION:one-use",
        )
        decision = gate.authorize(context)
        self.assertEqual("SIMULATED_MUTATION_AUTHORIZED", decision["decision"])
        with self.assertRaises(replay.MutationRefused):
            gate.authorize(context)

    def test_financial_mutation_gate_rejects_origin_confusion(self) -> None:
        gate = replay.FinancialMutationGate()
        confusing_origins = (
            "http://tradernet-sandbox.example",
            "https://tradernet-sandbox.example.attacker.invalid",
            "https://tradernet-sandbox.example/path",
            "https://tradernet-sandbox.example?next=production",
        )
        for index, origin in enumerate(confusing_origins):
            with self.subTest(origin=origin):
                nonce = f"origin-{index}"
                context = replay.MutationContext(
                    environment="sandbox",
                    origin=origin,
                    account_mode="sandbox",
                    mutation_enabled=True,
                    nonce=nonce,
                    confirmation=f"CONFIRM-SANDBOX-MUTATION:{nonce}",
                )
                with self.assertRaises(replay.MutationRefused):
                    gate.authorize(context)

    def test_secret_values_are_redacted_from_headers_and_text(self) -> None:
        result = replay.replay_secret_redaction()
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn("session-super-secret-1234567890", serialized)
        self.assertNotIn("bearer-super-secret-0987654321", serialized)
        self.assertTrue(result["guarded"]["invariant_pass"])

    def test_external_requests_have_explicit_bounded_timeout(self) -> None:
        transport = replay.FakeTransport()
        client = replay.BoundedHttpClient(transport, timeout_seconds=7.5)
        self.assertEqual({"status": 200, "simulated": True}, client.get())
        self.assertEqual([7.5], transport.timeouts)
        with self.assertRaises(ValueError):
            replay.BoundedHttpClient(transport, timeout_seconds=31.0)

    def test_html_report_escapes_diagnostics_and_environment(self) -> None:
        hostile = '<img src=x onerror="alert(1)">'
        rendered = replay.render_safe_html_report(hostile, hostile, hostile)
        self.assertNotIn(hostile, rendered)
        self.assertIn("&lt;img", rendered)
        self.assertNotIn("<img", rendered)

    def test_mock_skipped_unavailable_and_live_results_remain_distinct(self) -> None:
        result = replay.replay_evidence_classes()
        self.assertEqual(
            {
                "mock_pass": "SIMULATED_PASS",
                "skipped": "NOT_RUN",
                "unavailable": "UNAVAILABLE",
                "live_pass": "LIVE_PASS",
            },
            result["guarded"]["classifications"],
        )

    def test_full_replay_is_byte_deterministic(self) -> None:
        first = replay.canonical_json_bytes(replay.build_replay_result(SOURCE_SHA))
        second = replay.canonical_json_bytes(replay.build_replay_result(SOURCE_SHA))
        self.assertEqual(first, second)

    def test_full_replay_preserves_external_claim_boundary(self) -> None:
        result = replay.build_replay_result(SOURCE_SHA)
        self.assertEqual("NONE", result["external_product_claim"])
        self.assertFalse(result["network_access"])
        self.assertFalse(result["credential_use"])
        self.assertFalse(result["external_mutation"])
        self.assertTrue(result["mechanisms_reproduced"])
        self.assertTrue(result["all_guardrails_pass"])
        self.assertEqual(
            "CONFIRMED_LOCAL_MECHANISM_REPRODUCTION_AND_GUARDRAIL_PASS",
            result["verdict"],
        )

    def test_source_identity_requires_exact_lowercase_sha(self) -> None:
        invalid = ("main", "A" * 40, "a" * 39, "a" * 41, "g" * 40)
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    replay.build_replay_result(value)


if __name__ == "__main__":
    unittest.main()
