"""Validate complete credential capacity before any one-time key is requested."""

import json
import unittest

from deployment.credential_creation import prepare_credentials, runtime_record
from deployment.credential_errors import DeliveryError
from .record_fixtures import EXPIRES, IDENTITY, KEY_ID, NOW


class CredentialCreationTests(unittest.TestCase):
    def prepare(self, external="external-sentinel", password="demo-sentinel", expiry=EXPIRES):
        return prepare_credentials(IDENTITY, external, password, expiry, now=NOW)

    def test_generated_credentials_are_distinct_and_complete(self):
        first, second = self.prepare(), self.prepare()
        value = json.loads(runtime_record(first, KEY_ID, "model-sentinel").content)
        self.assertEqual(value["credentials"]["external_api_key"], "external-sentinel")
        self.assertEqual(value["credentials"]["demo_password"], "demo-sentinel")
        self.assertEqual(value["credentials"]["oci_api_key"], "model-sentinel")
        self.assertRegex(value["credentials"]["gateway_master_key"], r"^sk-[a-f0-9]{48}$")
        for name in ("database_password", "gateway_master_key", "gateway_salt_key"):
            self.assertNotEqual(first.credentials[name], second.credentials[name])
        self.assertNotEqual(first.intent.operation_id, second.intent.operation_id)
        self.assertNotIn("sentinel", repr(first))

    def test_invalid_supplied_credentials_are_rejected(self):
        for value in ("", None, 42, "secret\nline"):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(DeliveryError):
                    self.prepare(external=value)
                with self.assertRaises(DeliveryError):
                    self.prepare(password=value)

    def test_combined_serialized_size_reserves_capacity_for_model_key(self):
        for external, password in (("a" * 5000, "b" * 5000), ("é" * 4000, "p")):
            with self.subTest(input_bytes=len(external.encode())):
                with self.assertRaisesRegex(DeliveryError, "capacity"):
                    self.prepare(external, password)

    def test_expired_or_invalid_intent_is_rejected(self):
        for expiry in ("not-a-date", "2029-01-01T00:00:00Z"):
            with self.subTest(expiry=expiry):
                with self.assertRaises(DeliveryError):
                    self.prepare(expiry=expiry)

    def test_incomplete_identity_produces_a_sanitized_validation_error(self):
        with self.assertRaises(DeliveryError):
            prepare_credentials({}, "external", "password", EXPIRES, now=NOW)

    def test_unexpected_model_key_size_is_rejected_without_echoing_value(self):
        draft = self.prepare()
        for value in ("k" * 8193, "\\" * 4097):
            with self.subTest(length=len(value)):
                with self.assertRaises(DeliveryError) as error:
                    runtime_record(draft, KEY_ID, value)
                self.assertNotIn(value, str(error.exception))

    def test_reserved_capacity_accepts_supported_maximum_key_and_ocid(self):
        draft = self.prepare()
        prefix = "ocid1.generativeaiapikey.oc1.iad."
        value = runtime_record(draft, prefix + "a" * (512 - len(prefix)), "k" * 8192)
        self.assertLessEqual(len(value.content), 16384)
