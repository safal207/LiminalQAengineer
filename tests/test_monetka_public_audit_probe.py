import copy
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "monetka_public_audit_probe.py"
CONTRACT = ROOT / "audits" / "monetka" / "public-audit-v0.1" / "contract.json"

spec = importlib.util.spec_from_file_location("monetka_probe", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class MonetkaContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_baseline_contract_is_valid(self):
        module.validate_contract(self.contract)

    def test_rejects_authentication(self):
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["authentication"] = True
        with self.assertRaises(ValueError):
            module.validate_contract(changed)

    def test_rejects_cart_mutation(self):
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["cart_mutation"] = True
        with self.assertRaises(ValueError):
            module.validate_contract(changed)

    def test_rejects_order_creation(self):
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["order_creation"] = True
        with self.assertRaises(ValueError):
            module.validate_contract(changed)

    def test_rejects_external_contact(self):
        changed = copy.deepcopy(self.contract)
        changed["boundaries"]["email_or_external_contact"] = True
        with self.assertRaises(ValueError):
            module.validate_contract(changed)

    def test_rejects_unknown_origin(self):
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://example.com/"
        with self.assertRaises(ValueError):
            module.validate_contract(changed)

    def test_rejects_unlisted_url_on_allowed_origin(self):
        changed = copy.deepcopy(self.contract)
        changed["targets"][0]["url"] = "https://monetka.ru/admin/"
        with self.assertRaises(ValueError):
            module.validate_contract(changed)

    def test_none_of_assertion(self):
        assertion = {"id": "missing", "type": "none_of", "markers": ["25%", "20%"]}
        self.assertTrue(module.evaluate_assertion(assertion, "terms without value")["passed"])
        self.assertFalse(module.evaluate_assertion(assertion, "скидка 25%")["passed"])

    def test_disclosure_ceiling_is_preserved(self):
        observations = []
        for target in self.contract["targets"]:
            assertions = [
                {"id": assertion["id"], "type": assertion["type"], "passed": True}
                for assertion in target["assertions"]
            ]
            observations.append(
                module.Observation(
                    slug=target["slug"],
                    requested_url=target["url"],
                    final_url=target["url"],
                    status=200,
                    error=None,
                    content_type="text/html",
                    response_bytes=1,
                    body_sha256="x",
                    visible_text_sha256="y",
                    visible_text_length=1,
                    visible_text_sample="x",
                    origin_stayed_bounded=True,
                    assertions=assertions,
                )
            )
        result = module.build_result(self.contract, observations)
        states = {item["id"]: item["state"] for item in result["aggregate"]["findings"]}
        self.assertEqual(states["MON-006"], "PUBLIC_DISCLOSURE_SIGNAL_ONLY")


if __name__ == "__main__":
    unittest.main()
