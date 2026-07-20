from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "audits" / "chatgpt" / "authenticated-mobile-web-capture-v1.json"
SCRIPT_PATH = ROOT / "scripts" / "chatgpt_authenticated_mobile_web_capture.mjs"
DOC_PATH = ROOT / "docs" / "audits" / "CHATGPT_AUTHENTICATED_MOBILE_WEB_CAPTURE.md"


class ChatGPTAuthenticatedMobileWebCaptureContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.script = SCRIPT_PATH.read_text(encoding="utf-8")
        self.document = DOC_PATH.read_text(encoding="utf-8")

    def test_capture_is_local_attached_browser_only(self) -> None:
        self.assertEqual(self.config["target_origin"], "https://chatgpt.com")
        self.assertEqual(self.config["execution_mode"], "local_attached_browser_only")
        self.assertEqual(
            self.config["required_state"],
            "user_already_signed_in_in_the_attached_browser",
        )
        self.assertEqual(
            self.config["verdict_before_capture"],
            "PENDING_AUTHORIZED_LOCAL_EVIDENCE",
        )

    def test_private_session_and_content_are_not_exported(self) -> None:
        boundaries = self.config["boundaries"]
        privacy = self.config["privacy"]

        denied = {
            "credential_collection",
            "cookie_export",
            "storage_state_export",
            "raw_conversation_text_persistence",
            "network_request_body_capture",
            "network_response_body_capture",
            "automatic_navigation",
            "automatic_clicking",
            "automatic_typing",
            "automatic_prompt_submission",
            "automatic_file_upload",
            "microphone_permission_request",
            "camera_permission_request",
            "direct_application_api_testing",
            "access_control_bypass",
            "fuzzing",
            "load_testing",
            "active_security_testing",
            "external_submission",
            "deployment",
            "merge",
        }
        for key in denied:
            self.assertIs(boundaries[key], False, key)

        self.assertIs(privacy["persist_message_text"], False)
        self.assertIs(privacy["persist_chat_titles"], False)
        self.assertIs(privacy["persist_user_identity"], False)
        self.assertIs(privacy["persist_account_email"], False)
        self.assertIs(privacy["persist_full_url"], False)
        self.assertIs(privacy["screenshots_default"], False)
        self.assertIs(
            privacy["screenshots_require_explicit_acknowledgement"],
            True,
        )

    def test_script_attaches_but_does_not_drive_user_actions(self) -> None:
        required = {
            "puppeteer.connect",
            "browser.disconnect",
            "readline.createInterface",
            "AUTHENTICATED_LOCAL_EVIDENCE_CAPTURED_PENDING_ADJUDICATION",
            "--acknowledge-private-screenshot-risk",
            "text_sha256",
            "path_sha256",
        }
        for term in required:
            self.assertIn(term, self.script)

        prohibited = {
            "page.goto(",
            "page.click(",
            "element.click(",
            "page.type(",
            "keyboard.type(",
            "page.fill(",
            "page.authenticate(",
            "browserContext.cookies(",
            "page.cookies(",
            "localStorage.getItem(",
            "sessionStorage.getItem(",
            "request.postData(",
            "response.text(",
            "response.json(",
        }
        for term in prohibited:
            self.assertNotIn(term, self.script)

    def test_checkpoint_set_covers_real_mobile_chat_tasks(self) -> None:
        checkpoint_ids = {item["id"] for item in self.config["checkpoints"]}
        required = {
            "idle-long-chat",
            "return-to-latest",
            "composer-multiline-keyboard-open",
            "streaming-active",
            "stream-stopped-or-complete",
            "attachment-tray-open",
            "sidebar-history-open",
            "search-widget-or-source-panel",
            "offline",
            "recovered-online",
            "browser-zoom-200",
        }
        self.assertEqual(checkpoint_ids, required)

    def test_document_keeps_capture_and_adjudication_separate(self) -> None:
        required = {
            "PENDING_AUTHORIZED_LOCAL_EVIDENCE",
            "AUTHENTICATED_LOCAL_EVIDENCE_CAPTURED_PENDING_ADJUDICATION",
            "No external report, security claim, deployment, delivery or merge is authorised.",
            "LiminalQA exact evidence",
            "Pythia claim judgment",
            "CML canonical memory",
            "LS human-impact scorecard",
            "raw conversation text",
            "Screenshots are disabled by default",
        }
        for term in required:
            self.assertIn(term, self.document)


if __name__ == "__main__":
    unittest.main()
