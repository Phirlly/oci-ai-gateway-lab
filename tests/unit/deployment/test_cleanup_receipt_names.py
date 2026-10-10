"""Vault-compatible receipt names retain exact cleanup authority across upgrades."""

import unittest
from types import SimpleNamespace

from deployment.cleanup_keys import cleanup_keys
from deployment.cleanup_records import key_receipt
from deployment.cleanup_vault import CleanupVault
from deployment.credential_errors import CloudReadError, DeliveryError
from deployment.submission_records import digest
from .cleanup_vault_fixture import CleanupMemoryVault
from .key_cleanup_fixture import CleanupKeys
from .record_fixtures import KEY_ID, OPERATION
from .vault_fixture import delivery, record


class CleanupReceiptNameTests(unittest.TestCase):
    def setUp(self):
        self.vault = CleanupMemoryVault()
        self.vault.add(record('creation-intent'))
        self.store = CleanupVault(self.vault, delivery(self.vault).target, OPERATION)
        self.keys = CleanupKeys()
        self.legacy_name = 'removed-' + OPERATION + '-' + digest(KEY_ID)[:32]

    def remove(self):
        return cleanup_keys(self.keys, self.store, package_hash='a' * 64, config_hash='b' * 64)

    def receipt(self):
        return next((number, name, content) for number, (name, content) in self.vault.rows.items()
                    if name.startswith('removed-'))

    def test_remove_and_repeat_fit_service_limit_without_moving_current(self):
        self.assertTrue(self.remove())
        writes = list(self.vault.mutations)
        self.assertTrue(all(len(name) <= 50 for _, name, _ in writes))
        self.assertTrue(self.remove())
        self.assertEqual(self.vault.mutations, writes)
        self.assertEqual(self.vault.current, 1)
        self.assertEqual(len(self.keys.deleted), 1)

    def test_name_depends_on_full_operation_and_key(self):
        names = set()
        for operation in (OPERATION, 'b' * 32):
            for identifier in (KEY_ID, KEY_ID + 'other'):
                name, _ = key_receipt(SimpleNamespace(operation=operation), {}, identifier)
                self.assertLessEqual(len(name), 50)
                names.add(name)
        self.assertEqual(len(names), 4)

    def test_legacy_receipt_remains_authority_when_key_is_no_longer_observed(self):
        self.assertTrue(self.remove())
        number, _, content = self.receipt()
        self.vault.rows[number] = (self.legacy_name, content)
        self.keys.rows.clear()
        self.keys.get = lambda key: (_ for _ in ()).throw(CloudReadError('Not observed'))
        writes = list(self.vault.mutations)
        self.assertTrue(self.remove())
        self.assertEqual(self.vault.mutations, writes)
        self.assertEqual(len(self.keys.deleted), 1)

    def test_foreign_names_or_conflicting_aliases_block_cleanup(self):
        for variant in ('unknown-short', 'other-operation', 'changed-content', 'legacy-conflict'):
            self.setUp()
            self.assertTrue(self.remove())
            number, name, content = self.receipt()
            if variant == 'unknown-short':
                self.vault.rows[number] = ('removed-' + 'f' * 32, content)
            elif variant == 'other-operation':
                self.vault.rows[number] = ('removed-' + 'b' * 32 + '-' + digest(KEY_ID)[:32], content)
            elif variant == 'changed-content':
                self.vault.rows[number] = (name, b'{}')
            else:
                self.vault.add(SimpleNamespace(version_name=self.legacy_name, content=b'{}'))
            writes = list(self.vault.mutations)
            with self.subTest(variant=variant), self.assertRaises(DeliveryError):
                self.remove()
            self.assertEqual(self.vault.mutations, writes)
            self.assertEqual(len(self.keys.deleted), 1)

    def test_matching_legacy_and_new_receipts_do_not_duplicate_writes(self):
        self.assertTrue(self.remove())
        _, _, content = self.receipt()
        self.vault.add(SimpleNamespace(version_name=self.legacy_name, content=content))
        writes = list(self.vault.mutations)
        self.assertTrue(self.remove())
        self.assertEqual(self.vault.mutations, writes)
