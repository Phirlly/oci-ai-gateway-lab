"""Cleanup reads expired history without weakening credential delivery rules."""

import unittest
from datetime import timedelta

from deployment.cleanup_vault import CleanupVault
from deployment.credential_errors import DeliveryError
from deployment.vault_state import read_current
from .record_fixtures import NOW, OPERATION
from .vault_fixture import MemoryVault, delivery, record


class CleanupHistoryTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.target = delivery(self.vault).target
        self.store = CleanupVault(self.vault, self.target, OPERATION)

    def test_expired_runtime_is_cleanup_evidence_but_cannot_resume_delivery(self):
        self.vault.add(record('creation-intent'))
        self.vault.add(record(), current=True)
        history = self.store.read()
        self.assertEqual({item.kind for item in history.records}, {'creation-intent', 'runtime-bundle'})
        with self.assertRaises(DeliveryError):
            read_current(self.vault, self.target, NOW + timedelta(days=2))

    def test_manifest_can_displace_pending_label_without_losing_saved_key_identity(self):
        self.vault.add(record('creation-intent'))
        self.vault.add(record())
        self.vault.pending.clear()
        history = self.store.read()
        self.assertEqual(len(history.records), 2)
        self.assertEqual(history.current_number, 1)

    def test_foreign_unknown_duplicate_or_unpaired_history_stops(self):
        for variant in ('foreign', 'unknown', 'duplicate', 'unpaired'):
            self.vault = MemoryVault()
            self.store = CleanupVault(self.vault, self.target, OPERATION)
            self.vault.add(record(), current=True)
            if variant != 'unpaired':
                self.vault.add(record('creation-intent'))
            if variant == 'foreign':
                self.vault.metadata_overrides = {'compartment-id': 'foreign'}
            elif variant == 'unknown':
                self.vault.rows[4] = ('unknown', b'{}')
            elif variant == 'duplicate':
                self.vault.rows[4] = self.vault.rows[2]
            with self.subTest(variant=variant), self.assertRaises(DeliveryError):
                self.store.read()
