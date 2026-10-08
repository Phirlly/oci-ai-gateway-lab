"""Deletion uses owned metadata and never interprets absence as prior removal."""

import unittest
from copy import deepcopy

from deployment.credential_errors import DeliveryError
from deployment.model_key_cleanup import remove_model_keys
from .key_cleanup_fixture import CleanupKeys
from .record_fixtures import IDENTITY, KEY_ID


class ModelKeyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.keys = CleanupKeys()

    def remove(self, known=()):
        return remove_model_keys(self.keys, IDENTITY, known_key_ids=known)

    def test_owned_expired_key_is_removed_with_exact_etag_without_reading_credentials(self):
        self.keys.rows[0]['keys'] = [{'state': 'EXPIRED', 'time-expiry': '2000-01-01T00:00:00Z'}]
        result = self.remove((KEY_ID,))
        self.assertEqual(result.removed, (KEY_ID,))
        self.assertEqual(result.phase, 'KEYS_REMOVED')
        self.assertEqual(self.keys.deleted, [(KEY_ID, 'version-one')])

    def test_all_candidates_must_verify_before_first_deletion(self):
        other = deepcopy(self.keys.rows[0])
        other['id'] += 'other'
        self.keys.rows.append(other)
        original = self.keys.get

        def wrong_owner(identifier):
            value = original(identifier)
            if identifier == other['id']:
                value['data']['freeform-tags']['stack_ocid'] += 'changed'
            return value

        self.keys.get = wrong_owner
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertEqual(self.keys.deleted, [])

    def test_changed_operation_or_missing_etag_prevents_deletion(self):
        tags = dict(self.keys.rows[0]['freeform-tags'], operation_id='b' * 32)
        self.keys.get_changes = {'freeform-tags': tags}
        with self.assertRaises(DeliveryError):
            self.remove()
        self.keys.get_changes = {}
        self.keys.etag = ''
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertEqual(self.keys.deleted, [])

    def test_unrelated_key_is_preserved_and_wrong_region_stops(self):
        other = deepcopy(self.keys.rows[0])
        other.update({'id': KEY_ID + 'unrelated', 'display-name': 'other', 'freeform-tags': {}})
        self.keys.rows.append(other)
        self.remove()
        self.assertEqual(other['lifecycle-state'], 'ACTIVE')
        self.assertEqual(self.keys.deleted, [(KEY_ID, 'version-one')])
        self.keys.region = 'us-phoenix-1'
        with self.assertRaises(DeliveryError):
            self.remove()

    def test_deleting_is_pending_and_deleted_is_terminal_without_another_delete(self):
        self.keys.rows[0]['lifecycle-state'] = 'DELETING'
        self.assertEqual(self.remove().pending, (KEY_ID,))
        self.keys.rows[0]['lifecycle-state'] = 'DELETED'
        self.assertEqual(self.remove().removed, (KEY_ID,))
        self.assertEqual(self.keys.deleted, [])

    def test_empty_discovery_and_missing_known_key_are_not_removal_proof(self):
        self.keys.rows.clear()
        self.assertEqual(self.remove().phase, 'NO_KEYS_OBSERVED')
        result = self.remove((KEY_ID,))
        self.assertEqual(result.phase, 'UNRESOLVED')
        self.assertEqual(result.not_observed, (KEY_ID,))
        self.assertEqual(result.removed, ())

    def test_lost_reply_requires_exact_deleted_metadata_without_mutation_retry(self):
        self.keys.lose_reply = True
        self.assertEqual(self.remove().removed, (KEY_ID,))
        self.assertEqual(len(self.keys.deleted), 1)

    def test_unconfirmed_delete_keeps_key_pending(self):
        self.keys.commit_delete = False
        result = self.remove()
        self.assertEqual(result.phase, 'UNRESOLVED')
        self.assertEqual(result.pending, (KEY_ID,))
        self.assertEqual(len(self.keys.deleted), 1)
