"""Public recovery payloads contain hashes and operation identity only."""

import json
import unittest

from deployment.credential_errors import DeliveryError
from deployment.submission_records import (
    Intent, apply_request_hash, controller_identity, destroy_request_hash, target_identity,
)
from deployment.deployment_config import FoundationConfig
from .orm_fixtures import SETTINGS


class SubmissionRecordTests(unittest.TestCase):
    def test_payload_is_strict_and_contains_no_raw_settings(self):
        scope = target_identity(FoundationConfig(SETTINGS))
        intent = Intent('c' * 64, scope, 'create-stack', 'a' * 32, 'b' * 64, 'd' * 64)
        payload = intent.payload()
        self.assertEqual(Intent.parse(payload), intent)
        self.assertNotIn('ocid1.', json.dumps(payload))
        self.assertNotIn('gateway-test', json.dumps(payload))
        with self.assertRaises(DeliveryError):
            Intent.parse({**payload, 'credential': 'secret-sentinel'})

    def test_invalid_kind_identity_or_boolean_version_is_rejected(self):
        payload = Intent('c' * 64, 'd' * 64, 'apply', 'a' * 32, 'b' * 64, 'e' * 64).payload()
        for key, value in [('version', True), ('kind', 'unknown'), ('operation_id', ''), ('controller_id', 'raw')]:
            with self.subTest(key=key), self.assertRaises(DeliveryError):
                Intent.parse({**payload, key: value})

    def test_destroy_is_distinct_from_apply_with_the_same_config(self):
        value = Intent('c' * 64, 'd' * 64, 'destroy', 'a' * 32, 'b' * 64, 'e' * 64)
        self.assertEqual(Intent.parse(value.payload()), value)
        self.assertNotEqual(apply_request_hash('stack', SETTINGS, 'hash'),
                            destroy_request_hash('stack', SETTINGS, 'hash'))

    def test_controller_is_stable_by_repository_id_and_environment(self):
        self.assertEqual(controller_identity(17, 'Demo'), controller_identity(17, 'demo'))
        self.assertNotEqual(controller_identity(17, 'demo'), controller_identity(18, 'demo'))
        with self.assertRaises(DeliveryError):
            controller_identity(True, 'demo')
