"""Exact-version publication and recovery without refreshing stale ETags."""

import unittest

from deployment.credential_errors import DeliveryError
from .record_fixtures import KEY_ID
from .vault_fixture import MemoryVault, delivery, record


class CredentialPromotionTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.vault.add(record("creation-intent"))
        self.number = self.vault.add(record())
        self.delivery = delivery(self.vault)

    def test_exact_runtime_version_is_promoted_once_with_metadata_etag(self):
        etag = str(self.vault.etag)
        result = self.delivery.publish(record().version_name, KEY_ID)
        repeated = self.delivery.publish(record().version_name, KEY_ID)
        self.assertEqual(result, repeated)
        self.assertEqual((result.phase, result.version_number), ("CURRENT", self.number))
        self.assertEqual(self.vault.mutations, [("promote", self.number, etag)])

    def test_lost_promotion_reply_reconciles_current_without_another_mutation(self):
        self.vault.lose_promote_reply = True
        result = self.delivery.publish(record().version_name, KEY_ID)
        self.assertEqual(result.phase, "CURRENT")
        self.assertEqual(len(self.vault.mutations), 1)

    def test_intent_and_mismatched_binding_cannot_publish(self):
        for name, key in (
            (record("creation-intent").version_name, KEY_ID),
            (record().version_name, "ocid1.generativeaiapikey.oc1.ord.other"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(DeliveryError):
                    self.delivery.publish(name, key)
        self.assertEqual(self.vault.mutations, [])

    def test_concurrent_current_change_does_not_refresh_etag_or_overwrite(self):
        other = record(operation_id="b" * 32)
        self.vault.before_promote = lambda vault: vault.add(other, current=True)
        with self.assertRaises(DeliveryError):
            self.delivery.publish(record().version_name, KEY_ID)
        self.assertEqual(len(self.vault.mutations), 1)
        self.assertEqual(self.vault.rows[self.vault.current][0], other.version_name)

    def test_success_response_without_visible_current_is_not_success(self):
        def no_commit(secret_id, version_number, etag):
            self.vault.mutations.append(("promote", version_number, etag))
            return {"data": {}}
        self.vault.promote = no_commit
        with self.assertRaises(DeliveryError):
            self.delivery.publish(record().version_name, KEY_ID)
        self.assertEqual(len(self.vault.mutations), 1)

    def test_existing_different_current_is_preserved(self):
        other = record(operation_id="b" * 32)
        self.vault.add(other, current=True)
        with self.assertRaises(DeliveryError):
            self.delivery.publish(record().version_name, KEY_ID)
        self.assertEqual(self.vault.mutations, [])
