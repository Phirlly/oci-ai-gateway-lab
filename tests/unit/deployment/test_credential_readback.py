"""Delayed Vault reads preserve one-time creation and distinguish failure phases."""

import traceback
import unittest
from unittest.mock import patch

from deployment.credential_errors import ActivationPending, DeliveryError
from deployment.model_key_provisioning import ModelKeyProvisioner
from .model_key_fixture import MemoryKeys
from .record_fixtures import EXPIRES, KEY_ID
from .vault_fixture import MemoryVault, delivery
from .vault_transport_fixture import MemoryVaultTransport


class CredentialReadbackTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.transport = MemoryVaultTransport(self.vault)
        self.keys = MemoryKeys(self.vault)
        self.delivery = delivery(self.transport)
        self.provisioner = ModelKeyProvisioner(self.delivery, self.keys)
        self.sleep = patch("time.sleep").start()
        self.addCleanup(patch.stopall)

    def prepare(self):
        return self.provisioner.prepare(external_api_key="external-sentinel",
                                       demo_password="demo-sentinel", expires_at=EXPIRES)

    def delay_intent(self, count):
        self.transport.fail_when = lambda command, payload: (
            len(self.vault.rows) == 2 and "secretVersionName" in payload)
        self.transport.failures_remaining = count

    def delay_runtime(self, count):
        self.transport.fail_when = lambda command, payload: (
            bool(self.keys.created) and len(self.vault.rows) == 2
            and command[:3] == ("vault", "secret", "get"))
        self.transport.failures_remaining = count

    def test_delayed_intent_readback_creates_and_stores_exactly_once(self):
        self.delay_intent(3)
        self.assertEqual(self.prepare().phase, "PENDING")
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 2)
        self.assertEqual(self.sleep.call_count, 3)

    def test_delayed_runtime_preupload_read_preserves_returned_key(self):
        self.delay_runtime(2)
        result = self.prepare()
        self.assertEqual((result.phase, result.model_key_ocid), ("PENDING", KEY_ID))
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 2)
        self.assertIn(b"model-sentinel", self.vault.rows[3][1])

    def test_exhausted_intent_read_identifies_no_create_by_this_invocation(self):
        self.delay_intent(6)
        with self.assertRaisesRegex(DeliveryError, "No model-key creation was attempted by this invocation") as error:
            self.prepare()
        self.assertNotIn("sentinel", "".join(traceback.format_exception(error.exception)))
        self.assertEqual(self.keys.created, [])
        self.assertEqual(len(self.vault.mutations), 1)
        with self.assertRaisesRegex(DeliveryError, "explicit recovery"):
            self.prepare()
        self.assertEqual(self.keys.created, [])

    def test_exhausted_runtime_read_identifies_create_and_blocks_replay(self):
        self.delay_runtime(6)
        with self.assertRaisesRegex(DeliveryError, "Model-key creation returned") as error:
            self.prepare()
        self.assertNotIn("sentinel", "".join(traceback.format_exception(error.exception)))
        with self.assertRaisesRegex(DeliveryError, "explicit recovery"):
            self.prepare()
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 1)

    def test_delayed_publication_read_does_not_repeat_promotion(self):
        receipt = self.prepare()
        self.transport.fail_when = lambda command, payload: self.vault.current == 3
        self.transport.failures_remaining = 2
        result = self.delivery.publish(receipt.version_name, KEY_ID)
        self.assertEqual(result.phase, "CURRENT")
        self.assertEqual([m[0] for m in self.vault.mutations], ["stage", "stage", "promote"])

    def test_owned_metadata_failure_stops_immediately(self):
        self.vault.metadata_overrides["compartment-id"] = "wrong-owner"
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.assertEqual(len(self.transport.calls), 1)
        self.sleep.assert_not_called()
        self.assertEqual(self.vault.mutations, [])

    def test_key_activation_category_remains_pollable_after_saving(self):
        self.keys.read_changes = {"lifecycle-state": "CREATING"}
        with self.assertRaises(ActivationPending):
            self.prepare()
        self.assertEqual(self.delivery.reconcile().phase, "PENDING")
        self.assertEqual(len(self.keys.created), 1)
