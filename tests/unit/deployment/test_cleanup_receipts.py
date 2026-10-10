"""Retained private evidence permits deletion recovery without guessing absence."""

import json
import unittest

from deployment.cleanup_keys import cleanup_keys
from deployment.cleanup_vault import CleanupVault
from deployment.credential_errors import CloudReadError, DeliveryError
from .cleanup_vault_fixture import CleanupMemoryVault
from .key_cleanup_fixture import CleanupKeys
from .record_fixtures import KEY_ID, OPERATION
from .vault_fixture import delivery, record


class CleanupReceiptTests(unittest.TestCase):
    def setUp(self):
        self.vault = CleanupMemoryVault()
        self.vault.add(record('creation-intent'))
        self.vault.add(record(), current=True)
        self.store = CleanupVault(self.vault, delivery(self.vault).target, OPERATION)
        self.keys = CleanupKeys()

    def remove(self):
        return cleanup_keys(self.keys, self.store, package_hash='a' * 64, config_hash='b' * 64)

    def test_manifest_precedes_delete_receipt_survives_key_disappearance(self):
        delete = self.keys.delete

        def guarded_delete(key, etag):
            self.assertIn('cleanup-' + OPERATION, self.store.read().documents)
            delete(key, etag)

        self.keys.delete = guarded_delete
        self.assertTrue(self.remove())
        self.assertEqual(self.vault.current, 3)
        documents = self.store.read().documents
        self.assertEqual(len(documents), 2)
        self.assertNotIn('synthetic-oci_api_key', str(documents))
        self.keys.rows.clear()
        self.keys.get = lambda key: (_ for _ in ()).throw(CloudReadError('not observed'))
        self.assertTrue(self.remove())
        self.assertEqual(len(self.keys.deleted), 1)

    def test_unconfirmed_manifest_blocks_all_deletion(self):
        self.vault.reject_stage = True
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertEqual(self.keys.deleted, [])

    def test_confirmed_lost_manifest_reply_can_continue(self):
        self.vault.lose_stage_reply = True
        self.assertTrue(self.remove())
        self.assertEqual(len(self.keys.deleted), 1)

    def test_deleting_resumes_from_same_manifest_and_exact_deleted_state(self):
        self.keys.rows[0]['lifecycle-state'] = 'DELETING'
        self.assertFalse(self.remove())
        self.keys.rows[0]['lifecycle-state'] = 'DELETED'
        self.assertTrue(self.remove())
        self.assertEqual(self.keys.deleted, [])

    def test_ambiguous_get_after_lost_delete_never_claims_cleanup(self):
        self.keys.commit_delete = False
        self.assertFalse(self.remove())
        self.keys.rows.clear()
        self.keys.get = lambda key: (_ for _ in ()).throw(CloudReadError('not authorized or not found'))
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertEqual(len(self.store.read().documents), 1)

    def test_lost_creation_intent_with_no_key_observation_stops(self):
        self.vault.rows.pop(3)
        self.vault.current = 1
        self.keys.rows.clear()
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertFalse(self.vault.mutations)

    def test_changed_manifest_hash_or_key_owner_cannot_be_used(self):
        self.keys.rows[0]['lifecycle-state'] = 'DELETING'
        self.assertFalse(self.remove())
        with self.assertRaises(DeliveryError):
            cleanup_keys(self.keys, self.store, package_hash='c' * 64, config_hash='b' * 64)
        self.keys.get_changes = {'freeform-tags': {}}
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertEqual(self.keys.deleted, [])

    def test_initial_placeholder_with_no_records_or_candidates_is_proven_empty(self):
        self.vault = CleanupMemoryVault()
        self.store = CleanupVault(self.vault, delivery(self.vault).target, OPERATION)
        self.keys.rows.clear()
        self.assertTrue(self.remove())
        self.assertEqual(self.vault.current, 1)
