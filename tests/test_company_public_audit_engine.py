from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "scripts" / "company_public_audit_engine.py"
EXAMPLE_PATH = ROOT / "audits" / "templates" / "company-public-audit.example.json"

spec = importlib.util.spec_from_file_location("company_public_audit_engine", ENGINE_PATH)
assert spec and spec.loader
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class CompanyPublicAuditContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))

    def test_example_contract_is_valid_and_deterministic(self) -> None:
        first = engine.validate_config(copy.deepcopy(self.example))
        second = engine.validate_config(copy.deepcopy(self.example))
        self.assertEqual(first, second)
        self.assertEqual(first["company"]["name"], "Example Company")
        self.assertEqual(first["targets"][0]["url"], "https://example.com/")
        self.assertEqual(first["boundaries"], engine.REQUIRED_BOUNDARIES)
        self.assertEqual(
            engine.sha256_text(engine.canonical_json(first)),
            engine.sha256_text(engine.canonical_json(second)),
        )

    def test_matrix_contains_every_target_profile_cell(self) -> None:
        validated = engine.validate_config(copy.deepcopy(self.example))
        matrix = engine.build_matrix(validated)
        self.assertEqual(
            matrix,
            {
                "include": [
                    {
                        "target_id": "home",
                        "target_url": "https://example.com/",
                        "target_kind": "marketing",
                        "profile": "desktop",
                        "cell_id": "home-desktop",
                    },
                    {
                        "target_id": "home",
                        "target_url": "https://example.com/",
                        "target_kind": "marketing",
                        "profile": "mobile",
                        "cell_id": "home-mobile",
                    },
                ]
            },
        )

    def test_unknown_top_level_field_is_rejected(self) -> None:
        value = copy.deepcopy(self.example)
        value["custom_javascript"] = "fetch('/private')"
        with self.assertRaisesRegex(ValueError, "Unsupported top-level keys"):
            engine.validate_config(value)

    def test_credentials_and_custom_ports_are_rejected(self) -> None:
        for url in (
            "https://user:password@example.com/",
            "https://example.com:8443/",
        ):
            value = copy.deepcopy(self.example)
            value["targets"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                engine.validate_config(value)

    def test_private_and_local_network_targets_are_rejected(self) -> None:
        for origin in (
            "https://localhost",
            "https://127.0.0.1",
            "https://10.0.0.1",
            "https://192.168.1.20",
            "https://[::1]",
        ):
            value = copy.deepcopy(self.example)
            value["allowed_origins"] = [origin]
            value["targets"][0]["url"] = f"{origin}/"
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                engine.validate_config(value)

    def test_query_parameters_require_explicit_non_sensitive_allowlist(self) -> None:
        value = copy.deepcopy(self.example)
        value["targets"][0]["url"] = "https://example.com/chart?symbol=BTCUSD"
        with self.assertRaisesRegex(ValueError, "Query key is not allowlisted"):
            engine.validate_config(value)

        value["allowed_query_keys"] = ["symbol"]
        validated = engine.validate_config(value)
        self.assertEqual(validated["targets"][0]["url"], "https://example.com/chart?symbol=BTCUSD")

        sensitive = copy.deepcopy(self.example)
        sensitive["allowed_query_keys"] = ["access_token"]
        sensitive["targets"][0]["url"] = "https://example.com/?access_token=abc"
        with self.assertRaisesRegex(ValueError, "Sensitive-looking query key"):
            engine.validate_config(sensitive)

    def test_origin_escape_is_rejected(self) -> None:
        value = copy.deepcopy(self.example)
        value["targets"][0]["url"] = "https://other.example/"
        with self.assertRaisesRegex(ValueError, "outside allowed_origins"):
            engine.validate_config(value)

    def test_boundary_weakening_is_rejected(self) -> None:
        value = copy.deepcopy(self.example)
        value["boundaries"]["authenticated_testing"] = True
        with self.assertRaisesRegex(ValueError, "authenticated_testing must be false"):
            engine.validate_config(value)

        value = copy.deepcopy(self.example)
        del value["boundaries"]["load_testing"]
        with self.assertRaisesRegex(ValueError, "Boundary keys mismatch"):
            engine.validate_config(value)

    def test_target_and_profile_limits_are_enforced(self) -> None:
        value = copy.deepcopy(self.example)
        value["targets"] = [
            {"id": f"page-{index}", "url": f"https://example.com/{index}", "kind": "page"}
            for index in range(9)
        ]
        with self.assertRaisesRegex(ValueError, "1 to 8"):
            engine.validate_config(value)

        value = copy.deepcopy(self.example)
        value["profiles"] = ["desktop", "tablet"]
        with self.assertRaisesRegex(ValueError, "desktop, mobile"):
            engine.validate_config(value)

    def test_lighthouse_summary_uses_all_exact_runs(self) -> None:
        validated = engine.validate_config(copy.deepcopy(self.example))
        config_hash = engine.sha256_text(engine.canonical_json(validated))
        report = {
            "requestedUrl": "https://example.com/",
            "finalUrl": "https://example.com/",
            "fetchTime": "2026-07-20T00:00:00Z",
            "lighthouseVersion": "test",
            "categories": {
                "performance": {"score": 0.5},
                "accessibility": {"score": 0.9},
                "best-practices": {"score": 0.8},
                "seo": {"score": 1.0},
            },
            "audits": {
                "largest-contentful-paint": {"numericValue": 5000},
                "total-blocking-time": {"numericValue": 300},
                "unused-javascript": {
                    "score": 0.4,
                    "scoreDisplayMode": "numeric",
                    "title": "Reduce unused JavaScript",
                    "details": {"overallSavingsMs": 800},
                },
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "lhr-1.json").write_text(json.dumps(report), encoding="utf-8")
            summary = engine.summarize_lighthouse(
                validated,
                config_hash,
                "home",
                "desktop",
                root,
            )
        self.assertEqual(summary["verdict"], "WARN")
        self.assertEqual(summary["categories"]["performance"]["median_score"], 50)
        self.assertEqual(summary["core_metrics"]["largest_contentful_paint_ms"], 5000.0)
        self.assertEqual(summary["top_findings"][0]["audit_id"], "unused-javascript")

    def test_cell_classification_separates_navigation_and_quality_signals(self) -> None:
        browser = {
            "navigation": {"status": 200, "error": None},
            "signals": {
                "keyboard_focus_gap": True,
                "unnamed_sequential_controls": 1,
                "nested_interactive_controls": 0,
                "unnamed_accessibility_controls": 0,
            },
            "console": {"error_count": 0},
        }
        lighthouse = {"verdict": "PASS", "severity": "NONE"}
        result = engine.classify_cell(browser, lighthouse)
        self.assertEqual(result["verdict"], "WARN")
        self.assertEqual(result["severity"], "MEDIUM")
        self.assertIn("keyboard_focus_gap", result["reasons"])

        browser["navigation"] = {"status": 500, "error": None}
        result = engine.classify_cell(browser, lighthouse)
        self.assertEqual(result["severity"], "HIGH")
        self.assertIn("navigation_failed_or_non_success", result["reasons"])


if __name__ == "__main__":
    unittest.main()
