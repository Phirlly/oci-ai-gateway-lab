"""Versioned handoff binds runtime addressing and account/model configuration."""

import json
import unittest

from deployment.credential_creation import prepare_credentials, runtime_record
from deployment.credential_errors import DeliveryError
from deployment.credential_records import parse_record
from .record_fixtures import EXPIRES, IDENTITY, KEY_ID, NOW, document, encoded
from .gateway_config_fixture import CONTEXT


class RuntimeContextTests(unittest.TestCase):
    def test_context_is_preserved_from_creation_intent_to_runtime_bundle(self):
        draft = prepare_credentials(IDENTITY, "external", "Demo-test-Password9!", EXPIRES,
                                    now=NOW, runtime_context=CONTEXT)
        intent = json.loads(draft.intent.content)
        saved = json.loads(runtime_record(draft, KEY_ID, "model-key").content)
        self.assertEqual(intent["schema_version"], 2)
        self.assertEqual(saved["schema_version"], 2)
        self.assertEqual(saved["runtime"], CONTEXT)
        self.assertEqual(intent["runtime"], saved["runtime"])
        self.assertNotIn("runtime", saved["request"] if "request" in saved else {})

    def test_v1_record_and_canonical_serialization_remain_unchanged(self):
        value = document()
        parsed = json.loads(parse_record(encoded(value), IDENTITY).content)
        self.assertEqual(parsed, value)

    def test_context_cannot_redirect_runtime_to_private_address_or_unknown_provider(self):
        for field, bad in (("public_ip", "127.0.0.1"), ("public_ip", "169.254.169.254"),
                           ("public_ip", "https://example.test"), ("external_provider", "unknown"),
                           ("presenter_email", "bad"), ("instance_ocid", KEY_ID)):
            value = {**document(), "schema_version": 2, "runtime": {**CONTEXT, field: bad}}
            with self.subTest(field=field, bad=bad), self.assertRaises(DeliveryError):
                parse_record(encoded(value), IDENTITY)

    def test_v2_missing_context_and_v1_added_context_are_rejected(self):
        for value in ({**document(), "schema_version": 2}, {**document(), "runtime": CONTEXT}):
            with self.assertRaises(DeliveryError):
                parse_record(encoded(value), IDENTITY)

    def test_invalid_presenter_password_is_rejected_before_key_creation_intent(self):
        for password in ("short", "onlylowercasepassword", "NoDigitOrSymbolHere"):
            with self.subTest(password=password), self.assertRaises(DeliveryError):
                prepare_credentials(IDENTITY, "external", password, EXPIRES,
                                    now=NOW, runtime_context=CONTEXT)
