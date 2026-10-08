"""Named PENDING writes, exact readback and interrupted-upload recovery."""

import unittest
from deployment.credential_errors import DeliveryError
from deployment.credential_records import parse_record
from .record_fixtures import IDENTITY, document, encoded
from .vault_fixture import MemoryVault, delivery, record


class PendingDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.delivery = delivery(self.vault)

    def test_intent_and_runtime_stage_separately_and_matching_rerun_does_not_write(self):
        intent = self.delivery.stage(record("creation-intent"))
        staged = self.delivery.stage(record())
        repeated = self.delivery.stage(record())
        self.assertEqual(intent.phase, "INTENT")
        self.assertEqual(staged.phase, "PENDING")
        self.assertEqual(staged, repeated)
        self.assertEqual(len(self.vault.mutations), 2)
        self.assertEqual(self.vault.current, 1)

    def test_runtime_requires_matching_durable_creation_intent(self):
        with self.assertRaisesRegex(DeliveryError, "intent"):
            self.delivery.stage(record())
        self.assertEqual(self.vault.mutations, [])

    def test_lost_upload_response_recovers_exact_version_without_second_write(self):
        self.vault.lose_stage_reply = True
        receipt = self.delivery.stage(record("creation-intent"))
        self.assertEqual(receipt.phase, "INTENT")
        self.assertEqual(len(self.vault.mutations), 1)
        self.assertEqual(receipt.version_number, 2)

    def test_uncertain_upload_without_visible_version_stops_without_retry(self):
        self.vault.reject_stage = True
        with self.assertRaises(DeliveryError):
            self.delivery.stage(record("creation-intent"))
        self.assertEqual(len(self.vault.mutations), 1)

    def test_current_preserves_existing_credentials_despite_changed_inputs(self):
        current = record()
        number = self.vault.add(current, current=True)
        changed = document()
        changed["credentials"]["demo_password"] = "different-incoming-password"
        result = self.delivery.stage(parse_record(encoded(changed), IDENTITY))
        self.assertEqual((result.phase, result.version_number), ("CURRENT", number))
        self.assertEqual(self.vault.rows[number][1], current.content)
        self.assertEqual(self.vault.mutations, [])

    def test_same_named_pending_version_with_changed_content_is_rejected(self):
        self.vault.add(record("creation-intent"))
        self.vault.add(record())
        changed = document()
        changed["credentials"]["external_api_key"] = "different-incoming-key"
        with self.assertRaises(DeliveryError):
            self.delivery.stage(parse_record(encoded(changed), IDENTITY))
        self.assertEqual(self.vault.mutations, [])

    def test_other_pending_operation_cannot_be_overwritten(self):
        self.vault.add(record("creation-intent"))
        with self.assertRaises(DeliveryError):
            self.delivery.stage(record(operation_id="b" * 32))
        self.assertEqual(self.vault.mutations, [])
