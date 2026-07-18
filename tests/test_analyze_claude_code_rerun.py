#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "analyze_claude_code_rerun.py"
spec = importlib.util.spec_from_file_location("analyze_claude_code_rerun", MODULE_PATH)
assert spec and spec.loader
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


def report(*, lcp: float | None, tbt: float | None, performance: float | None, error: str | None = None) -> dict:
    lcp_audit = {
        "score": None if error else 0.5,
        "scoreDisplayMode": "error" if error else "numeric",
    }
    tbt_audit = {
        "score": None if error else 0.5,
        "scoreDisplayMode": "error" if error else "numeric",
    }
    if lcp is not None:
        lcp_audit["numericValue"] = lcp
    if tbt is not None:
        tbt_audit["numericValue"] = tbt
    if error:
        lcp_audit["errorMessage"] = error
        tbt_audit["errorMessage"] = error
    return {
        "requestedUrl": analyzer.TARGET,
        "finalDisplayedUrl": analyzer.TARGET,
        "fetchTime": "2026-07-19T00:00:00Z",
        "runtimeError": None,
        "categories": {
            "performance": {"score": performance},
            "accessibility": {"score": 0.9},
            "best-practices": {"score": 0.9},
            "seo": {"score": 0.9},
        },
        "audits": {
            "largest-contentful-paint": lcp_audit,
            "total-blocking-time": tbt_audit,
            "first-contentful-paint": {"score": 0.8, "scoreDisplayMode": "numeric", "numericValue": 2000},
            "speed-index": {"score": 0.8, "scoreDisplayMode": "numeric", "numericValue": 3000},
            "diagnostics": {"details": {"items": [{"numRequests": 10}]}}
        },
    }


class ClaudeCodeRerunTests(unittest.TestCase):
    def write_reports(self, root: Path, values: list[dict]) -> list[Path]:
        paths = []
        for index, value in enumerate(values, start=1):
            path = root / f"lhr-{index}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            paths.append(path)
        return paths

    def test_valid_lcp_repeated_supersedes_no_lcp_measurement_state(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self.write_reports(Path(raw), [
                report(lcp=10000, tbt=500, performance=0.4),
                report(lcp=12000, tbt=700, performance=0.3),
                report(lcp=None, tbt=None, performance=None, error="NO_LCP"),
            ])
            result = analyzer.build_result(paths)
            self.assertEqual(result["result"]["state"], "VALID_LCP_REPEATED")
            self.assertEqual(result["result"]["valid_lcp_runs"], 2)
            self.assertEqual(result["result"]["median_lcp_ms"], 11000.0)
            self.assertTrue(result["interpretation"]["supersession_allowed"])
            self.assertFalse(result["interpretation"]["performance_zero_is_product_score"])

    def test_repeated_no_lcp_remains_measurement_conflict_not_score_zero(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self.write_reports(Path(raw), [
                report(lcp=None, tbt=None, performance=None, error="NO_LCP"),
                report(lcp=None, tbt=None, performance=None, error="NO_LCP"),
                report(lcp=9000, tbt=300, performance=0.5),
            ])
            result = analyzer.build_result(paths)
            self.assertEqual(result["result"]["state"], "NO_LCP_REPEATED")
            self.assertEqual(result["result"]["no_lcp_runs"], 2)
            self.assertFalse(result["interpretation"]["supersession_allowed"])
            self.assertFalse(result["interpretation"]["performance_zero_is_product_score"])

    def test_exactly_three_reports_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self.write_reports(Path(raw), [report(lcp=10000, tbt=500, performance=0.4)])
            with self.assertRaisesRegex(ValueError, "requires 3"):
                analyzer.build_result(paths)

    def test_redirect_or_wrong_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            values = [report(lcp=10000, tbt=500, performance=0.4) for _ in range(3)]
            values[1]["finalDisplayedUrl"] = "https://claude.com/"
            paths = self.write_reports(Path(raw), values)
            with self.assertRaisesRegex(ValueError, "unexpected URL"):
                analyzer.build_result(paths)


if __name__ == "__main__":
    unittest.main()
