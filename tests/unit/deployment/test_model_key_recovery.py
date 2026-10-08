"""Interrupted creation never authorizes a second key or replacement."""

import unittest
from unittest.mock import patch

from deployment.credential_creation import prepare_credentials
from deployment.credential_errors import DeliveryError
from deployment.model_key_provisioning import ModelKeyProvisioner
from .model_key_fixture import MemoryKeys, key_data
from .record_fixtures import EXPIRES, IDENTITY, KEY_ID, NOW
from .vault_fixture import MemoryVault, delivery, record


class ModelKeyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.keys = MemoryKeys(self.vault)
        self.delivery = delivery(self.vault)
        self.provisioner = ModelKeyProvisioner(self.delivery, self.keys)

    def prepare(self, **changes):
        inputs = dict(external_api_key="external-sentinel", demo_password="demo-sentinel", expires_at=EXPIRES)
        return self.provisioner.prepare(**(inputs | changes))

    def test_resumed_intent_stops_even_when_listing_is_empty(self):
        self.vault.add(record("creation-intent"))
        with self.assertRaisesRegex(DeliveryError, "recovery"):
            self.prepare()
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_lost_create_reply_cannot_create_again_even_if_key_is_not_listed(self):
        self.keys.lose_reply = True
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.keys.rows.clear()
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 1)

    def test_oversized_combined_inputs_stop_before_intent_or_key_creation(self):
        with self.assertRaises(DeliveryError):
            self.prepare(external_api_key="e" * 5000, demo_password="p" * 5000)
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_existing_owned_key_without_bundle_requires_recovery(self):
        self.keys.rows = [key_data()]
        with self.assertRaisesRegex(DeliveryError, "recovery"):
            self.prepare()
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_uncertain_intent_write_prevents_key_creation(self):
        self.vault.lose_stage_reply = True
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.delivery.reconcile().phase, "INTENT")

    def test_unusable_create_response_preserves_intent_and_cannot_retry(self):
        self.keys.create_changes = {"keys": []}
        with self.assertRaises(DeliveryError):
            self.prepare()
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(self.delivery.reconcile().phase, "INTENT")

    def test_failed_runtime_storage_preserves_intent_and_blocks_recreation(self):
        original = self.delivery.stage

        def fail_runtime(value, **options):
            if value.kind == "runtime-bundle":
                raise DeliveryError("Synthetic unavailable Vault.")
            return original(value, **options)

        with patch.object(self.delivery, "stage", side_effect=fail_runtime):
            with self.assertRaises(DeliveryError):
                self.prepare()
        with self.assertRaises(DeliveryError):
            self.prepare()
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(self.delivery.reconcile().phase, "INTENT")

    def test_conflicting_stack_binding_stops_before_creation(self):
        with self.assertRaises(DeliveryError):
            self.prepare(stack_key_ocid=KEY_ID)
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_reused_intent_discovered_during_claim_cannot_authorize_create(self):
        draft = prepare_credentials(IDENTITY, "external", "password", EXPIRES, now=NOW)

        def expose_existing_intent(compartment):
            self.vault.add(draft.intent)
            return {"data": {"items": []}}

        with patch("deployment.model_key_provisioning.prepare_credentials", return_value=draft):
            with patch.object(self.keys, "list", side_effect=expose_existing_intent):
                with self.assertRaises(DeliveryError):
                    self.prepare()
        self.assertEqual(self.keys.created, [])
        self.assertEqual(self.vault.mutations, [])

    def test_lost_runtime_upload_reply_is_recovered_without_another_key(self):
        original = self.delivery.stage

        def lose_runtime_reply(value, **options):
            self.vault.lose_stage_reply = value.kind == "runtime-bundle"
            return original(value, **options)

        with patch.object(self.delivery, "stage", side_effect=lose_runtime_reply):
            result = self.prepare()
        self.assertEqual(result.phase, "PENDING")
        self.assertEqual(self.provisioner.prepare(), result)
        self.assertEqual(len(self.keys.created), 1)
        self.assertEqual(len(self.vault.mutations), 2)
