"""Only a confirmed new intent upload can authorize a one-time creation."""

import unittest

from deployment.credential_errors import DeliveryError
from .vault_fixture import MemoryVault, delivery, record


class IntentClaimTests(unittest.TestCase):
    def test_confirmed_new_intent_can_be_claimed(self):
        vault = MemoryVault()
        result = delivery(vault).stage(record("creation-intent"), fresh_intent=True)
        self.assertEqual(result.phase, "INTENT")
        self.assertEqual(len(vault.mutations), 1)

    def test_existing_named_intent_cannot_be_claimed_again(self):
        vault = MemoryVault()
        vault.add(record("creation-intent"))
        with self.assertRaises(DeliveryError):
            delivery(vault).stage(record("creation-intent"), fresh_intent=True)
        self.assertEqual(vault.mutations, [])

    def test_uncertain_intent_upload_remains_recovery_only_even_when_saved(self):
        vault = MemoryVault()
        vault.lose_stage_reply = True
        with self.assertRaises(DeliveryError):
            delivery(vault).stage(record("creation-intent"), fresh_intent=True)
        self.assertEqual(delivery(vault).reconcile().phase, "INTENT")
        self.assertEqual(len(vault.mutations), 1)

    def test_current_credentials_stop_a_fresh_claim_without_write(self):
        vault = MemoryVault()
        vault.add(record(), current=True)
        result = delivery(vault).stage(record("creation-intent"), fresh_intent=True)
        self.assertEqual(result.phase, "CURRENT")
        self.assertEqual(vault.mutations, [])

    def test_runtime_record_cannot_request_fresh_intent_semantics(self):
        vault = MemoryVault()
        with self.assertRaises(DeliveryError):
            delivery(vault).stage(record(), fresh_intent=True)
        self.assertEqual(vault.mutations, [])
