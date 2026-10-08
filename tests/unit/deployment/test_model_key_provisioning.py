"""Successful preparation and reuse stop before ORM binding or publication."""

import json
import unittest
from unittest.mock import patch

from deployment.credential_errors import DeliveryError
from deployment.model_key_provisioning import ModelKeyProvisioner
from .model_key_fixture import MemoryKeys, key_data
from .record_fixtures import EXPIRES, KEY_ID
from .vault_fixture import MemoryVault, delivery, record


class ModelKeyProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.keys = MemoryKeys(self.vault)
        self.delivery = delivery(self.vault)
        self.provisioner = ModelKeyProvisioner(self.delivery, self.keys)

    def prepare(self, **changes):
        inputs = dict(external_api_key="external-sentinel", demo_password="demo-sentinel", expires_at=EXPIRES)
        return self.provisioner.prepare(**(inputs | changes))

    def test_one_key_is_stored_before_readiness_and_never_automatically_published(self):
        def check_saved():
            bundle = json.loads(self.vault.rows[3][1])
            self.assertEqual(bundle["credentials"]["oci_api_key"], "model-sentinel")
        self.keys.before_get = check_saved
        result = self.prepare()
        self.assertEqual((result.phase, result.model_key_ocid), ("PENDING", KEY_ID))
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 2)
        self.assertEqual(self.vault.current, 1)
        self.assertNotIn("sentinel", repr(result))

    def test_pending_rerun_preserves_all_credentials_and_never_creates_again(self):
        result = self.prepare()
        saved = self.vault.rows[result.version_number][1]
        repeated = self.prepare(external_api_key="changed", demo_password="changed")
        self.assertEqual(result, repeated)
        self.assertEqual(self.vault.rows[result.version_number][1], saved)
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 2)

    def test_current_rerun_does_not_require_new_secret_inputs(self):
        self.keys.rows = [key_data()]
        self.vault.add(record(), current=True)
        result = self.provisioner.prepare(stack_key_ocid=KEY_ID)
        self.assertEqual(result.phase, "CURRENT")
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_creating_response_is_saved_before_successful_active_read(self):
        self.keys.create_changes = {"lifecycle-state": "CREATING"}
        self.keys.read_changes = {"lifecycle-state": "ACTIVE"}
        self.assertEqual(self.prepare().phase, "PENDING")
        self.assertEqual(len(self.vault.rows), 3)

    def test_inactive_read_retains_bundle_and_resume_reuses_it(self):
        self.keys.read_changes = {"lifecycle-state": "CREATING"}
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.assertEqual(self.delivery.reconcile().phase, "PENDING")
        self.keys.read_changes.clear()
        self.assertEqual(self.provisioner.prepare().phase, "PENDING")
        self.assertEqual(len(self.keys.created), 1)

    def test_current_appearing_during_intent_claim_prevents_creation(self):
        original = self.delivery.stage

        def concurrent_current(value, **options):
            self.vault.add(record(), current=True)
            self.keys.rows = [key_data()]
            return original(value, **options)

        with patch.object(self.delivery, "stage", side_effect=concurrent_current):
            self.assertEqual(self.prepare().phase, "CURRENT")
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_wrong_inference_region_is_rejected_before_any_write(self):
        self.keys.region = "us-ashburn-1"
        with self.assertRaises(DeliveryError):
            ModelKeyProvisioner(self.delivery, self.keys)
        self.assertEqual(self.vault.mutations, [])
