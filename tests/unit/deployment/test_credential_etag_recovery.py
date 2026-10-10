"""Rejected uploads may retry only after complete credential-state validation."""

from datetime import timedelta
import unittest
from unittest.mock import patch

from deployment.credential_errors import DeliveryError
from deployment.credential_records import parse_record
from .record_fixtures import IDENTITY, NOW, document, encoded
from .vault_conflict_fixture import ETagRejectingVault
from .vault_fixture import delivery, record


class CredentialETagRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.vault = ETagRejectingVault()
        self.vault.add(record('creation-intent'))
        self.delivery = delivery(self.vault)
        self.sleep = patch('time.sleep').start()
        self.addCleanup(patch.stopall)

    def test_rejection_revalidates_and_uploads_identical_runtime_with_new_etag(self):
        result = self.delivery.stage(record())
        self.assertEqual(result.phase, 'PENDING')
        first, second = self.vault.attempts
        self.assertEqual(first[:3], second[:3])
        self.assertNotEqual(first[3], second[3])
        self.assertEqual(self.vault.rows[result.version_number][1], record().content)
        self.assertEqual(len(self.vault.mutations), 1)
        self.sleep.assert_called_once_with(1)

    def test_three_rejections_stop_without_committing_or_rotating(self):
        self.vault.rejections_remaining = 10
        with self.assertRaisesRegex(DeliveryError, 'conditional upload'):
            self.delivery.stage(record())
        self.assertEqual(len(self.vault.attempts), 3)
        self.assertEqual(self.vault.mutations, [])
        self.assertEqual(self.vault.current, 1)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 2])

    def test_owner_change_stops_before_second_write(self):
        self.vault.after_rejection = lambda: self.vault.metadata_overrides.update({'compartment-id': 'other'})
        with self.assertRaisesRegex(DeliveryError, 'metadata'):
            self.delivery.stage(record())
        self.assertEqual(len(self.vault.attempts), 1)

    def test_other_operation_in_history_stops_before_second_write(self):
        other = parse_record(encoded(document('creation-intent', operation='b' * 32)), IDENTITY)
        self.vault.after_rejection = lambda: self.vault.add(other)
        with self.assertRaisesRegex(DeliveryError, 'Conflicting'):
            self.delivery.stage(record())
        self.assertEqual(len(self.vault.attempts), 1)

    def test_expiry_during_backoff_stops_before_second_write(self):
        self.sleep.side_effect = lambda seconds: setattr(self.delivery, 'now', lambda: NOW + timedelta(days=3))
        with self.assertRaisesRegex(DeliveryError, 'expired'):
            self.delivery.stage(record())
        self.assertEqual(len(self.vault.attempts), 1)

    def test_new_current_is_preserved_without_another_write(self):
        other = record(operation_id='b' * 32)
        self.vault.after_rejection = lambda: self.vault.add(other, current=True)
        result = self.delivery.stage(record())
        self.assertEqual((result.phase, result.version_name), ('CURRENT', other.version_name))
        self.assertEqual(self.vault.rows[self.vault.current][1], other.content)
        self.assertEqual(len(self.vault.attempts), 1)

    def test_identical_runtime_appearing_after_rejection_is_reused(self):
        self.vault.after_rejection = lambda: self.vault.add(record())
        result = self.delivery.stage(record())
        self.assertEqual((result.phase, result.version_name), ('PENDING', record().version_name))
        self.assertEqual(len(self.vault.attempts), 1)

    def test_rejection_then_lost_committed_reply_uses_readback_without_third_write(self):
        self.vault.lose_stage_reply = True
        result = self.delivery.stage(record())
        self.assertEqual(result.phase, 'PENDING')
        self.assertEqual(len(self.vault.attempts), 2)
        self.assertEqual(len(self.vault.mutations), 1)

    def test_rejection_then_unknown_uncommitted_write_never_retries(self):
        self.vault.reject_stage = True
        with self.assertRaises(DeliveryError):
            self.delivery.stage(record())
        self.assertEqual(len(self.vault.attempts), 2)
        self.assertEqual(len(self.vault.rows), 2)
