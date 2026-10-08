"""CURRENT precedence, ownership and ambiguous recovery decisions."""

import unittest

from deployment.credential_errors import DeliveryError
from .record_fixtures import KEY_ID
from .vault_fixture import MemoryVault, delivery, record


class KeyBindingTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.delivery = delivery(self.vault)

    def test_initial_placeholder_has_no_model_binding(self):
        result = self.delivery.reconcile()
        self.assertEqual(result.phase, "UNCONFIGURED")
        self.assertIsNone(result.model_key_ocid)

    def test_current_is_authoritative_over_older_pending_intent(self):
        self.vault.add(record("creation-intent"))
        number = self.vault.add(record(), current=True)
        result = self.delivery.reconcile(KEY_ID)
        self.assertEqual((result.phase, result.version_number, result.model_key_ocid),
                         ("CURRENT", number, KEY_ID))
        self.assertNotIn("synthetic-", repr(result))
        self.assertEqual(self.vault.mutations, [])

    def test_pending_runtime_supplies_binding_only_while_current_unconfigured(self):
        self.vault.add(record("creation-intent"))
        number = self.vault.add(record())
        result = self.delivery.reconcile()
        self.assertEqual((result.phase, result.version_number), ("PENDING", number))
        self.assertEqual(result.model_key_ocid, KEY_ID)

    def test_conflicting_stack_binding_fails_without_mutation(self):
        self.vault.add(record(), current=True)
        with self.assertRaises(DeliveryError):
            self.delivery.reconcile("ocid1.generativeaiapikey.oc1.ord.other")
        self.assertEqual(self.vault.mutations, [])

    def test_current_malformed_expired_or_intent_cannot_fall_back_to_pending(self):
        for content in (b"malformed", record("creation-intent").content,
                        record(expires_at="2029-12-31T00:00:00Z").content):
            with self.subTest(content_type=content[:20]):
                vault = MemoryVault()
                vault.rows[1] = ("unconfigured", content)
                vault.add(record())
                with self.assertRaises(DeliveryError):
                    delivery(vault).reconcile()
                self.assertEqual(vault.mutations, [])

    def test_multiple_pending_operations_stop_reconciliation(self):
        self.vault.add(record())
        self.vault.add(record(operation_id="b" * 32))
        with self.assertRaisesRegex(DeliveryError, "pending"):
            self.delivery.reconcile()
        self.assertEqual(self.vault.mutations, [])

    def test_wrong_resource_ownership_or_inactive_secret_stops_before_write(self):
        changes = [
            {"vault-id": "other"}, {"key-id": "other"},
            {"compartment-id": "other"}, {"lifecycle-state": "PENDING_DELETION"},
            {"freeform-tags": {"solution": "other", "deployment_id": "gateway-test"}},
        ]
        for changed in changes:
            with self.subTest(changed=changed):
                self.vault.metadata_overrides = changed
                with self.assertRaises(DeliveryError):
                    self.delivery.stage(record("creation-intent"))
                self.assertEqual(self.vault.mutations, [])

    def test_binding_without_durable_runtime_record_cannot_authorize_recreate(self):
        with self.assertRaises(DeliveryError):
            self.delivery.reconcile(KEY_ID)
