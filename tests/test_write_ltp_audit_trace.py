import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "write_ltp_audit_trace.py"
spec = importlib.util.spec_from_file_location("write_ltp_audit_trace", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry.json"
        self.registry.write_text(json.dumps({"actions": {"send_message": {}, "transfer_money": {}}}), encoding="utf-8")
        self.critical, _ = module.load_registry(self.registry)
        timestamp = "2026-07-27T00:00:00.000Z"
        continuity = "ct-test"
        frames = [
            ("out", module.make_frame("step-1", timestamp, "hello", {"agent": "test"}, None)),
            ("out", module.make_frame("step-2", timestamp, "orientation", {"identity": "repo@sha", "status": "healthy"}, continuity)),
            ("out", module.make_frame("step-3", timestamp, "focus_snapshot", {"drift": 0.0}, continuity)),
            ("in", module.make_frame("step-4", timestamp, "route_request", {"goal": "observe"}, continuity)),
            ("out", module.make_frame("step-5", timestamp, "route_response", {"context": "CI", "targetState": "capture_public_evidence", "admissible": True, "decision": "EXECUTE", "branches": [{"id": "a", "confidence": 1.0, "status": "admissible"}]}, continuity)),
        ]
        self.entries = module.build_entries(frames, "session-1")

    def tearDown(self):
        self.temp.cleanup()

    def test_js_numeric_canonicalization(self):
        self.assertEqual(module.canon({"x": 0.0, "y": [1.0, 1.5]}), b'{"x":0,"y":[1,1.5]}')

    def test_clean_trace_passes(self):
        result = module.verify_entries(self.entries, self.critical)
        self.assertTrue(result["valid"])
        self.assertEqual(result["frames"], 5)

    def test_tampered_frame_fails(self):
        entries = copy.deepcopy(self.entries)
        entries[3]["frame"]["payload"]["goal"] = "tampered"
        with self.assertRaisesRegex(module.TraceContractError, "event hash mismatch"):
            module.verify_entries(entries, self.critical)

    def test_reordered_entries_fail(self):
        entries = copy.deepcopy(self.entries)
        entries[2], entries[3] = entries[3], entries[2]
        with self.assertRaises(module.TraceContractError):
            module.verify_entries(entries, self.critical)

    def test_duplicate_frame_id_fails(self):
        entries = copy.deepcopy(self.entries)
        entries[2]["frame"]["id"] = entries[1]["frame"]["id"]
        entries = module.build_entries([(entry["direction"], entry["frame"]) for entry in entries], "session-1")
        with self.assertRaisesRegex(module.TraceContractError, "duplicate frame id"):
            module.verify_entries(entries, self.critical)

    def test_session_identity_change_fails(self):
        entries = copy.deepcopy(self.entries)
        entries[-1]["session_id"] = "other-session"
        with self.assertRaisesRegex(module.TraceContractError, "session identity changed"):
            module.verify_entries(entries, self.critical)

    def test_unsupported_version_fails(self):
        entries = copy.deepcopy(self.entries)
        entries[0]["frame"]["v"] = "9.9"
        entries = module.build_entries([(entry["direction"], entry["frame"]) for entry in entries], "session-1")
        with self.assertRaisesRegex(module.TraceContractError, "unsupported frame version"):
            module.verify_entries(entries, self.critical)

    def test_malformed_jsonl_fails(self):
        path = self.root / "bad.jsonl"
        path.write_text('{"i":0}\n{"broken"\n', encoding="utf-8")
        with self.assertRaisesRegex(module.TraceContractError, "invalid JSONL"):
            module.parse_jsonl(path)

    def test_web_direct_critical_action_fails(self):
        timestamp = "2026-07-27T00:00:00.000Z"
        continuity = "ct-test"
        frames = [
            ("out", module.make_frame("step-1", timestamp, "orientation", {"identity": "repo@sha"}, continuity)),
            ("out", module.make_frame("step-2", timestamp, "route_response", {"context": "WEB", "targetState": "send_message", "admissible": True, "decision": "EXECUTE", "branches": [{"id": "unsafe", "confidence": 1.0, "status": "admissible"}]}, continuity)),
        ]
        entries = module.build_entries(frames, "session-1")
        with self.assertRaisesRegex(module.TraceContractError, "critical WEB-direct action"):
            module.verify_entries(entries, self.critical)


if __name__ == "__main__":
    unittest.main()
