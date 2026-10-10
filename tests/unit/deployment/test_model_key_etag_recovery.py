"""Staging rejection recovery never repeats model-key creation."""

import unittest
from unittest.mock import patch

from deployment.credential_errors import DeliveryError
from deployment.credential_records import parse_record
from deployment.model_key_provisioning import ModelKeyProvisioner
from .model_key_fixture import MemoryKeys
from .record_fixtures import EXPIRES, IDENTITY
from .vault_conflict_fixture import ETagRejectingVault
from .vault_fixture import delivery


class ModelKeyETagRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.vault = ETagRejectingVault()
        self.keys = MemoryKeys(self.vault)
        self.delivery = delivery(self.vault)
        self.provisioner = ModelKeyProvisioner(self.delivery, self.keys)
        patch('time.sleep').start()
        self.addCleanup(patch.stopall)

    def prepare(self):
        return self.provisioner.prepare(external_api_key='external-sentinel',
                                       demo_password='demo-sentinel', expires_at=EXPIRES)

    def assert_recovers_one_key(self, kind):
        self.vault.reject_kind = kind
        result = self.prepare()
        self.assertEqual(result.phase, 'PENDING')
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.attempts), 3)
        self.assertEqual(len(self.vault.mutations), 2)
        self.assertIn(b'model-sentinel', self.vault.rows[result.version_number][1])
        self.assertEqual(self.prepare(), result)
        self.assertEqual(len(self.keys.created), 1)

    def test_rejected_intent_recovers_with_only_one_key_creation(self):
        self.assert_recovers_one_key('creation-intent')

    def test_rejected_runtime_recovers_with_only_one_key_creation(self):
        self.assert_recovers_one_key('runtime-bundle')

    def test_existing_fresh_intent_after_rejection_cannot_authorize_creation(self):
        self.vault.reject_kind = 'creation-intent'
        self.vault.after_rejection = lambda: self.vault.add(parse_record(self.vault.attempts[-1][2], IDENTITY))
        with self.assertRaisesRegex(DeliveryError, 'No model-key creation'):
            self.prepare()
        self.assertEqual(self.keys.created, [])
        self.assertEqual(len(self.vault.attempts), 1)

    def test_rejection_then_uncertain_intent_cannot_authorize_creation(self):
        self.vault.reject_kind = 'creation-intent'
        self.vault.lose_stage_reply = True
        with self.assertRaisesRegex(DeliveryError, 'No model-key creation'):
            self.prepare()
        self.assertEqual(self.keys.created, [])
        self.assertEqual(len(self.vault.attempts), 2)
        self.assertEqual(len(self.vault.rows), 2)

    def test_exhausted_runtime_rejections_preserve_intent_and_block_future_creation(self):
        self.vault.rejections_remaining = 10
        with self.assertRaisesRegex(DeliveryError, 'Model-key creation returned'):
            self.prepare()
        self.assertEqual(len(self.vault.attempts), 4)
        with self.assertRaisesRegex(DeliveryError, 'explicit recovery'):
            self.prepare()
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.rows), 2)
