"""Strict schema and ownership checks for persisted credential records."""

import unittest
from copy import deepcopy

from deployment.credential_errors import DeliveryError
from deployment.credential_records import parse_record
from .record_fixtures import IDENTITY, NOW, OPERATION, document, encoded


class CredentialRecordTests(unittest.TestCase):
    def test_runtime_roundtrip_is_canonical_and_repr_hides_secrets(self):
        value = document()
        record = parse_record(encoded(value), IDENTITY)
        self.assertEqual(record.version_name, "runtime-" + OPERATION)
        self.assertEqual(record.kind, "runtime-bundle")
        self.assertEqual(record, parse_record(record.content, IDENTITY))
        self.assertNotIn("synthetic-", repr(record))
        record.require_unexpired(NOW)

    def test_exact_nonsecret_intent_is_a_distinct_record_type(self):
        record = parse_record(encoded(document("creation-intent")), IDENTITY)
        self.assertEqual(record.version_name, "intent-" + OPERATION)
        self.assertIsNone(record.model_key_ocid)
        self.assertNotIn("synthetic-", record.content.decode())

    def test_wrong_identity_unknown_fields_or_missing_secret_are_rejected(self):
        for change in ("identity", "unknown", "missing", "intent_secret"):
            with self.subTest(change=change):
                value = document()
                if change == "identity":
                    value["identity"]["stack_ocid"] += "other"
                elif change == "unknown":
                    value["private_key"] = "sensitive-sentinel"
                elif change == "missing":
                    del value["credentials"]["gateway_salt_key"]
                else:
                    value = document("creation-intent")
                    value["request"]["key"] = "sensitive-sentinel"
                with self.assertRaises(DeliveryError) as error:
                    parse_record(encoded(value), IDENTITY)
                self.assertNotIn("sensitive-sentinel", str(error.exception))

    def test_duplicate_json_keys_and_non_objects_are_rejected(self):
        for raw in (b'{"kind":"a","kind":"b"}', b"[]", b"null", b"bad secret"):
            with self.subTest(raw=raw):
                with self.assertRaises(DeliveryError):
                    parse_record(raw, IDENTITY)

    def test_invalid_schema_types_expiry_and_identifiers_are_rejected(self):
        changes = [
            ("schema_version", True), ("schema_version", 2),
            ("operation_id", "../unsafe"), ("expires_at", "not-a-date"),
            ("expires_at", "2030-01-02T00:00:00"),
            ("model_key_ocid", "ocid1.key.oc1.iad.example"),
            ("model_key_ocid", "ocid1.generativeaiapikey.oc1..example"),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                changed = document()
                changed[field] = value
                with self.assertRaises(DeliveryError):
                    parse_record(encoded(changed), IDENTITY)

    def test_identity_itself_is_validated_not_just_compared(self):
        bad = deepcopy(IDENTITY)
        bad["compartment_ocid"] = "not-an-ocid"
        value = document()
        value["identity"] = bad
        with self.assertRaises(DeliveryError):
            parse_record(encoded(value), bad)

    def test_record_over_size_limit_and_control_characters_are_rejected(self):
        for secret in ("x" * 17000, "hidden\nvalue", ""):
            with self.subTest(size=len(secret)):
                value = document()
                value["credentials"]["external_api_key"] = secret
                with self.assertRaises(DeliveryError):
                    parse_record(encoded(value), IDENTITY)

    def test_expired_record_requires_recovery_instead_of_rotation(self):
        value = document()
        value["expires_at"] = "2029-12-31T00:00:00Z"
        record = parse_record(encoded(value), IDENTITY)
        with self.assertRaisesRegex(DeliveryError, "expired"):
            record.require_unexpired(NOW)

    def test_intent_request_must_match_identity_expiry_and_retry_policy(self):
        for field in ("retry_policy", "compartmentId", "timeExpiry"):
            with self.subTest(field=field):
                value = document("creation-intent")
                if field == "retry_policy":
                    value[field] = "retry"
                elif field == "compartmentId":
                    value["request"][field] += "other"
                else:
                    value["request"]["keyDetails"][0][field] = "2030-01-03T00:00:00Z"
                with self.assertRaises(DeliveryError):
                    parse_record(encoded(value), IDENTITY)
