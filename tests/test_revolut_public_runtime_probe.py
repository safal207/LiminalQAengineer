from __future__ import annotations

import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "revolut_public_runtime_probe.py"
spec = importlib.util.spec_from_file_location("revolut_public_runtime_probe", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class RevolutPublicRuntimeProbeTest(unittest.TestCase):
    def test_request_contains_no_authentication_or_cookie_headers(self):
        request = module.build_request("https://example.test/public")
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(headers["user-agent"], module.USER_AGENT)
        self.assertEqual(headers["accept"], "application/json")
        for forbidden in (
            "authorization",
            "x-revx-api-key",
            "x-revx-timestamp",
            "x-revx-signature",
            "cookie",
        ):
            self.assertNotIn(forbidden, headers)
        self.assertIsNone(request.data)

    def test_last_trades_schema_summary_keeps_shape_not_values(self):
        payload = {
            "data": [
                {
                    "tdt": "2026-07-19T00:00:00Z",
                    "aid": "BTC",
                    "p": "60000.00",
                    "tid": "secret-looking-but-public-trade-id",
                }
            ],
            "metadata": {"timestamp": "2026-07-19T00:00:01Z"},
        }
        summary = module.summarize_json("last_trades", payload)
        self.assertTrue(summary["contract_ok"])
        self.assertEqual(summary["item_count"], 1)
        self.assertEqual(summary["metadata_timestamp_type"], "string")
        self.assertEqual(summary["first_item_keys"], ["aid", "p", "tdt", "tid"])
        rendered = str(summary)
        self.assertNotIn("60000.00", rendered)
        self.assertNotIn("secret-looking-but-public-trade-id", rendered)

    def test_order_book_summary_records_counts_and_sorting(self):
        payload = {
            "data": {
                "asks": [{"p": "101"}, {"p": "100"}],
                "bids": [{"p": "99"}, {"p": "98"}],
            },
            "metadata": {"timestamp": "2026-07-19T00:00:01Z"},
        }
        summary = module.summarize_json("order_book_btc_usd", payload)
        self.assertTrue(summary["contract_ok"])
        self.assertEqual(summary["ask_count"], 2)
        self.assertEqual(summary["bid_count"], 2)
        self.assertIs(summary["asks_descending"], True)
        self.assertIs(summary["bids_descending"], True)

    def test_invalid_price_makes_sorting_unknown_not_false(self):
        self.assertIsNone(module.is_descending(module.decimal_prices([{"p": "not-a-decimal"}])))
        self.assertIs(module.is_descending([Decimal("2"), Decimal("1")]), True)

    def test_classification_separates_auth_network_and_schema_results(self):
        self.assertEqual(module.classify(200, True), "PUBLIC_NO_AUTH_CONFIRMED")
        self.assertEqual(module.classify(401, False), "AUTH_REQUIRED_AT_RUNTIME")
        self.assertEqual(module.classify(403, False), "AUTH_REQUIRED_AT_RUNTIME")
        self.assertEqual(module.classify(None, False), "NETWORK_UNAVAILABLE")
        self.assertEqual(module.classify(200, False), "RUNTIME_RESPONSE_MISMATCH")

    def test_run_probe_enforces_two_requests_and_spacing(self):
        observations = [
            {"classification": "PUBLIC_NO_AUTH_CONFIRMED"},
            {"classification": "NETWORK_UNAVAILABLE"},
        ]
        sleeps: list[float] = []
        with patch.object(module, "probe_endpoint", side_effect=observations) as probe:
            report = module.run_probe(sleeper=sleeps.append)
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(sleeps, [module.SPACING_SECONDS])
        self.assertEqual(report["constraints"]["request_count"], 2)
        self.assertIs(report["constraints"]["auth_headers_sent"], False)
        self.assertIs(report["constraints"]["raw_response_body_persisted"], False)
        self.assertEqual(report["summary"]["public_no_auth_confirmed"], 1)
        self.assertEqual(report["summary"]["network_unavailable"], 1)


if __name__ == "__main__":
    unittest.main()
