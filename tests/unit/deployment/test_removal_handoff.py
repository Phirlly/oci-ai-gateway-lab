"""Remove records cleanup once and resumes Destroy without VM or Vault access."""

import unittest
from copy import deepcopy

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from deployment.removal_handoff import advance_removal
from deployment.stack_submission import ensure_stack
from deployment.submission_records import target_identity
from .cleanup_vault_fixture import CleanupMemoryVault
from .destroy_fixture import destroy_fixture
from .inventory_fixture import inventory
from .key_cleanup_fixture import CleanupKeys
from .record_fixtures import IDENTITY
from .vault_fixture import record


class RemovalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = destroy_fixture()
        self.stack = ensure_stack(self.f.orm, self.f.journal, self.f.target, self.f.package)
        self.f.orm.list_job_resources = lambda *args: inventory()
        self.vault = CleanupMemoryVault()
        self.vault.region = self.f.target.config.values['region']
        self.keys = CleanupKeys()

    def apply(self):
        f = self.f
        ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id, model_key_ocid=None)

    def remove(self):
        f = self.f
        return advance_removal(f.orm, f.journal, f.target, f.package, vault=self.vault,
                               keys=self.keys, inference_region=IDENTITY['inference_region'])

    def test_successful_base_cleans_keys_before_recording_and_submitting_destroy(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.vault.add(record('creation-intent'))
        self.vault.add(record(), current=True)
        result = self.remove()
        self.assertEqual(result.phase, 'DESTROY')
        self.assertEqual(len(self.keys.deleted), 1)
        records = self.f.journal.read(target_identity(self.f.target.config))
        kinds = [row.kind for row in records]
        self.assertLess(kinds.index('cleanup-start'), kinds.index('cleanup-complete'))
        self.assertLess(kinds.index('cleanup-complete'), kinds.index('destroy'))
        self.vault = None
        self.keys = None
        self.f.orm.jobs[-1]['lifecycle-state'] = 'SUCCEEDED'
        self.assertEqual(self.remove().job.state, 'SUCCEEDED')
        self.assertEqual(len(self.f.orm.jobs), 2)

    def test_partial_base_failure_can_remove_without_vault_or_model_keys(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.vault = None
        self.keys = None
        self.assertEqual(self.remove().phase, 'DESTROY')

    def test_active_apply_does_not_begin_key_cleanup(self):
        self.apply()
        self.assertEqual(self.remove().phase, 'WAIT_FOR_INFRASTRUCTURE')
        self.assertFalse(self.keys.deleted)
        records = self.f.journal.read(target_identity(self.f.target.config))
        self.assertNotIn('cleanup-start', [row.kind for row in records])

    def test_pending_key_deletion_blocks_destroy_and_later_deploy(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.vault.add(record('creation-intent'))
        self.keys.rows[0]['lifecycle-state'] = 'DELETING'
        self.assertEqual(self.remove().phase, 'KEY_DELETION_PENDING')
        self.assertEqual(len(self.f.orm.jobs), 1)
        with self.assertRaises(DeliveryError):
            self.apply()
        self.keys.rows[0]['lifecycle-state'] = 'DELETED'
        self.assertEqual(self.remove().phase, 'DESTROY')

    def test_missing_saved_key_stops_before_destroy(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.vault.add(record('creation-intent'))
        self.keys.rows.clear()
        with self.assertRaises(DeliveryError):
            self.remove()
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_completion_cannot_be_reused_after_configuration_changes(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.remove()
        self.f.orm.stacks[0]['variables']['oci_model_id'] = 'different'
        with self.assertRaises(DeliveryError):
            self.remove()
