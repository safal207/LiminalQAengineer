from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "audits" / "chatgpt" / "unauthenticated-mobile-chat-journey-v1.json"
SCRIPT = ROOT / "scripts" / "chatgpt_unauthenticated_mobile_chat_journey.mjs"
DOC = ROOT / "docs" / "audits" / "CHATGPT_UNAUTHENTICATED_MOBILE_CHAT_JOURNEY.md"


class ChatGPTUnauthenticatedMobileChatJourneyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.script = SCRIPT.read_text(encoding="utf-8")
        self.doc = DOC.read_text(encoding="utf-8")

    def test_scope_is_one_public_benign_prompt(self) -> None:
        self.assertEqual(self.config["target_url"], "https://chatgpt.com/")
        self.assertEqual(self.config["prompt"], "Reply with exactly: MOBILE WEB OK")
        self.assertEqual(self.config["expected_response_fragment"], "MOBILE WEB OK")
        self.assertIs(self.config["boundaries"]["public_unauthenticated_only"], True)
        self.assertIs(self.config["boundaries"]["single_benign_prompt"], True)
        self.assertEqual(self.config["boundaries"]["maximum_prompt_submissions"], 1)

    def test_forbidden_actions_remain_disabled(self) -> None:
        boundaries = self.config["boundaries"]
        for key in {
            "login_submission",
            "account_access",
            "file_upload",
            "microphone_permission",
            "camera_permission",
            "direct_application_api_testing",
            "captcha_or_access_control_bypass",
            "fuzzing",
            "load_testing",
            "active_security_testing",
            "private_data_collection",
            "external_reporting",
            "deployment",
            "merge",
        }:
            self.assertIs(boundaries[key], False, key)

    def test_script_has_one_prompt_entry_and_one_send_click(self) -> None:
        self.assertEqual(self.script.count("page.keyboard.type(config.prompt"), 1)
        self.assertEqual(self.script.count("await sendHandle.click()"), 1)
        self.assertNotIn("page.goto('https://chatgpt.com/auth/login", self.script)
        self.assertNotIn("request.postData(", self.script)
        self.assertNotIn("response.text(", self.script)
        self.assertNotIn("response.json(", self.script)
        self.assertNotIn("page.setRequestInterception", self.script)
        self.assertNotIn("browserContext.cookies(", self.script)
        self.assertNotIn("page.cookies(", self.script)

    def test_result_does_not_persist_raw_response_text(self) -> None:
        self.assertIn("response_text_sha256", self.script)
        self.assertIn("response_text_length", self.script)
        self.assertNotIn("response_text: responseText", self.script)
        self.assertIn("text_sha256", self.script)
        self.assertIn("UNAUTHENTICATED_MOBILE_CHAT_PASS", self.script)

    def test_document_keeps_interaction_and_claim_boundary_explicit(self) -> None:
        for term in {
            "exactly one product action sequence",
            "does not log in or access an account",
            "does not persist raw response text",
            "A detector signal is not automatically a product defect",
            "does not authorise external reporting",
        }:
            self.assertIn(term, self.doc)


if __name__ == "__main__":
    unittest.main()
