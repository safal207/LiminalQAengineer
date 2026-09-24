from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "write_exact_head_manifest.py"
spec = importlib.util.spec_from_file_location("write_exact_head_manifest", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

SHA = "a" * 40
WORKFLOW_SHA = "b" * 40


class ExactHeadManifestTests(unittest.TestCase):
    def test_manifest_hashes_files_and_binds_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "result.json").write_text('{"ok":true}\n', encoding="utf-8")
            args = argparse.Namespace(
                output_dir=str(output_dir),
                manifest_name="manifest.json",
                audit_name="test audit",
                target="https://example.test/",
                repository="owner/repo",
                expected_sha=SHA,
                initial_sha=SHA,
                final_sha=SHA,
                workflow_sha=WORKFLOW_SHA,
                event_name="pull_request",
                git_ref="refs/pull/1/merge",
                head_ref="agent/test",
                workflow_ref="owner/repo/.github/workflows/test.yml@refs/pull/1/merge",
                run_id="123",
                run_attempt="2",
                artifact_name="evidence-123-2",
                started_at="2026-07-27T00:00:00Z",
                completed_at="2026-07-27T00:00:01Z",
                execution_status="success",
            )
            module.manifest_command(args)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["source_identity"]["head_stable"])
            self.assertEqual(manifest["run_identity"]["run_attempt"], "2")
            self.assertEqual([item["path"] for item in manifest["files"]], ["result.json"])
            self.assertEqual(
                manifest["files"][0]["sha256"],
                module.sha256_file(output_dir / "result.json"),
            )

    def test_manifest_rejects_head_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                output_dir=tmp,
                manifest_name="manifest.json",
                audit_name="test",
                target="https://example.test/",
                repository="owner/repo",
                expected_sha=SHA,
                initial_sha=SHA,
                final_sha="c" * 40,
                workflow_sha=WORKFLOW_SHA,
                event_name="push",
                git_ref="refs/heads/main",
                head_ref="",
                workflow_ref="workflow",
                run_id="1",
                run_attempt="1",
                artifact_name="evidence-1-1",
                started_at="2026-07-27T00:00:00Z",
                completed_at="2026-07-27T00:00:01Z",
                execution_status="success",
            )
            with self.assertRaisesRegex(ValueError, "must match"):
                module.manifest_command(args)

    def test_receipt_binds_uploaded_artifact_to_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "result.txt").write_text("evidence\n", encoding="utf-8")
            manifest_args = argparse.Namespace(
                output_dir=str(root),
                manifest_name="manifest.json",
                audit_name="test",
                target="https://example.test/",
                repository="owner/repo",
                expected_sha=SHA,
                initial_sha=SHA,
                final_sha=SHA,
                workflow_sha=WORKFLOW_SHA,
                event_name="push",
                git_ref="refs/heads/main",
                head_ref="",
                workflow_ref="workflow",
                run_id="7",
                run_attempt="3",
                artifact_name="evidence-7-3",
                started_at="2026-07-27T00:00:00Z",
                completed_at="2026-07-27T00:00:01Z",
                execution_status="success",
            )
            module.manifest_command(manifest_args)
            receipt_path = root / "receipt" / "artifact-receipt.json"
            receipt_args = argparse.Namespace(
                manifest=str(root / "manifest.json"),
                output=str(receipt_path),
                artifact_name="evidence-7-3",
                artifact_id="999",
                artifact_url="https://example.test/artifacts/999",
                artifact_digest="sha256:" + "d" * 64,
                run_id="7",
                run_attempt="3",
            )
            module.receipt_command(receipt_args)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["artifact"]["id"], "999")
            self.assertEqual(receipt["artifact"]["sha256"], "d" * 64)
            self.assertEqual(
                receipt["manifest"]["sha256"],
                module.sha256_file(root / "manifest.json"),
            )


if __name__ == "__main__":
    unittest.main()
