"""Reject unverified API version identities and inconsistent staged records."""

import unittest
from unittest.mock import patch

from deployment.credential_errors import DeliveryError
from deployment.credential_records import parse_record
from .record_fixtures import IDENTITY, KEY_ID, document, encoded
from .vault_fixture import MemoryVault, delivery, record


class VaultVersionTests(unittest.TestCase):
    def test_bundle_identity_number_name_and_encoding_are_verified(self):
        changes = [
            {"secret-id": "other"}, {"version-number": 99},
            {"version-name": "different"},
            {"secret-bundle-content": {"content-type": "BASE64", "content": "invalid!"}},
        ]
        for changed in changes:
            with self.subTest(changed=changed):
                vault = MemoryVault()
                original = vault.bundle

                def altered(*args, **kwargs):
                    response = original(*args, **kwargs)
                    response["data"].update(changed)
                    return response

                with patch.object(vault, "bundle", side_effect=altered):
                    with self.assertRaises(DeliveryError):
                        delivery(vault).reconcile()
                self.assertEqual(vault.mutations, [])

    def test_duplicate_version_list_entries_do_not_select_arbitrary_candidate(self):
        vault = MemoryVault()
        vault.add(record("creation-intent"))
        response = vault.versions("ocid1.vaultsecret.oc1.iad.example")
        response["data"].append(dict(response["data"][-1]))
        with patch.object(vault, "versions", return_value=response):
            with self.assertRaises(DeliveryError):
                delivery(vault).reconcile()

    def test_current_version_change_between_metadata_and_bundle_stops(self):
        vault = MemoryVault()
        original = vault.bundle

        def changed_current(*args, **kwargs):
            vault.add(record(), current=True)
            return original(*args, **kwargs)

        with patch.object(vault, "bundle", side_effect=changed_current):
            with self.assertRaises(DeliveryError):
                delivery(vault).stage(record("creation-intent"))
        self.assertEqual(vault.mutations, [])

    def test_pending_runtime_without_intent_cannot_supply_a_binding(self):
        vault = MemoryVault()
        vault.add(record())
        with self.assertRaisesRegex(DeliveryError, "intent"):
            delivery(vault).reconcile()
        with self.assertRaises(DeliveryError):
            delivery(vault).publish(record().version_name, KEY_ID)
        self.assertEqual(vault.mutations, [])

    def test_pending_runtime_expiry_must_match_durable_intent(self):
        vault = MemoryVault()
        vault.add(record("creation-intent"))
        vault.add(record(expires_at="2030-01-03T00:00:00Z"))
        with self.assertRaises(DeliveryError):
            delivery(vault).reconcile()
        self.assertEqual(vault.mutations, [])

    def test_displaced_intent_is_recovered_without_reupload(self):
        vault = MemoryVault()
        intent = record("creation-intent")
        number = vault.add(intent)
        vault.pending.remove(number)
        service = delivery(vault)
        recovered = service.reconcile()
        self.assertEqual((recovered.phase, recovered.version_number), ("INTENT", number))
        self.assertEqual(service.stage(intent), recovered)
        self.assertEqual(vault.mutations, [])

    def test_runtime_recovery_and_publication_do_not_require_pending_intent_stage(self):
        vault = MemoryVault()
        intent_number = vault.add(record("creation-intent"))
        runtime = record()
        runtime_number = vault.add(runtime)
        vault.pending.remove(intent_number)
        service = delivery(vault)
        recovered = service.reconcile(KEY_ID)
        self.assertEqual((recovered.phase, recovered.version_number), ("PENDING", runtime_number))
        self.assertEqual(service.stage(runtime), recovered)
        self.assertEqual(vault.mutations, [])
        self.assertEqual(service.publish(runtime.version_name, KEY_ID).phase, "CURRENT")
        self.assertEqual(len(vault.mutations), 1)

    def test_conflicting_older_intent_cannot_be_ignored_when_stage_changes(self):
        vault = MemoryVault()
        other = parse_record(encoded(document("creation-intent", operation="b" * 32)), IDENTITY)
        old_number = vault.add(other)
        vault.pending.remove(old_number)
        vault.add(record("creation-intent"))
        vault.add(record())
        with self.assertRaises(DeliveryError):
            delivery(vault).reconcile()
        self.assertEqual(vault.mutations, [])

    def test_runtime_without_pending_stage_requires_recovery_not_reupload(self):
        vault = MemoryVault()
        vault.add(record("creation-intent"))
        runtime = record()
        number = vault.add(runtime)
        vault.pending.remove(number)
        service = delivery(vault)
        with self.assertRaises(DeliveryError):
            service.reconcile()
        with self.assertRaises(DeliveryError):
            service.stage(runtime)
        with self.assertRaises(DeliveryError):
            service.publish(runtime.version_name, KEY_ID)
        self.assertEqual(vault.mutations, [])
