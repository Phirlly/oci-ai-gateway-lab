"""A pending or current bundle cannot silently acquire different runtime settings."""

import unittest

from deployment.credential_errors import DeliveryError
from deployment.model_key_provisioning import ModelKeyProvisioner
from .model_key_fixture import MemoryKeys
from .record_fixtures import EXPIRES
from .gateway_config_fixture import CONTEXT
from .vault_fixture import MemoryVault, delivery, record


class ContextPreservationTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.delivery = delivery(self.vault)

    def test_runtime_staging_rejects_context_different_from_durable_intent(self):
        self.vault.add(record("creation-intent", schema_version=2, runtime=CONTEXT))
        changed = {**CONTEXT, "public_ip": "8.8.8.8"}
        with self.assertRaises(DeliveryError):
            self.delivery.stage(record(schema_version=2, runtime=changed))
        self.assertEqual(self.vault.mutations, [])

    def test_resume_rejects_already_stored_context_conflict(self):
        self.vault.add(record("creation-intent", schema_version=2, runtime=CONTEXT))
        changed = {**CONTEXT, "external_model_id": "different-model"}
        self.vault.add(record(schema_version=2, runtime=changed))
        with self.assertRaises(DeliveryError):
            self.delivery.reconcile()

    def test_provisioner_preserves_v2_on_resume_and_rejects_requested_drift(self):
        keys = MemoryKeys(self.vault)
        provisioner = ModelKeyProvisioner(self.delivery, keys)
        saved = provisioner.prepare(
            external_api_key="synthetic", demo_password="Demo-test-Password9!",
            expires_at=EXPIRES, runtime_context=CONTEXT,
        )
        self.assertEqual(provisioner.prepare(runtime_context=CONTEXT), saved)
        with self.assertRaises(DeliveryError):
            provisioner.prepare(runtime_context={**CONTEXT, "public_ip": "8.8.8.8"})
        self.assertEqual(len(keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 2)
