"""Reruns preserve saved credentials and never turn uncertainty into new writes."""

import unittest

from deployment.credential_errors import DeliveryError, MutationUncertain
from .handoff_fixture import HandoffFixture
from .record_fixtures import EXPIRES
from .vault_fixture import record


class HandoffResumeTests(unittest.TestCase):
    def setUp(self):
        self.f = HandoffFixture()

    def test_pending_permission_job_preserves_bundle_despite_changed_creation_inputs(self):
        initial = self.f.permissions_started()
        saved = dict(self.f.vault.rows)
        for state in ('ACCEPTED', 'IN_PROGRESS', 'CANCELING', 'FAILED', 'CANCELED'):
            self.f.orm.jobs[1]['lifecycle-state'] = state
            with self.subTest(state=state):
                result = self.f.advance(external_api_key='changed', demo_password='changed',
                                        expires_at='invalid-new-expiry')
                self.assertEqual((result.phase, result.job.state), ('PERMISSIONS', state))
                self.assertEqual(result.credentials, initial.credentials)
        self.assertEqual(self.f.vault.rows, saved)
        self.assertEqual(self.f.vault.current, 1)
        self.assertEqual(len(self.f.keys.created), 1)
        self.assertEqual(len(self.f.orm.jobs), 2)

    def test_current_rerun_needs_no_creation_inputs_and_does_not_rotate_or_resubmit(self):
        self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        initial = self.f.advance()
        saved, writes = dict(self.f.vault.rows), list(self.f.vault.mutations)
        result = self.f.advance()
        self.assertEqual(result, initial)
        self.assertEqual(self.f.vault.rows, saved)
        self.assertEqual(self.f.vault.mutations, writes)
        self.assertEqual(len(self.f.keys.created), 1)
        self.assertEqual(len(self.f.orm.jobs), 2)

    def test_lost_permission_reply_recovers_job_and_saved_bundle(self):
        self.f.base_succeeded()
        self.f.orm.fail = 'create_apply'
        with self.assertRaises(MutationUncertain):
            self.f.advance(external_api_key='external', demo_password='password', expires_at=EXPIRES)
        self.f.orm.fail = None
        self.assertEqual(self.f.advance().phase, 'PERMISSIONS')
        self.assertEqual(len(self.f.orm.jobs), 2)
        self.assertEqual(len(self.f.keys.created), 1)

    def test_lost_promotion_reply_recovers_exact_current_once(self):
        self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        self.f.vault.lose_promote_reply = True
        self.assertEqual(self.f.advance().phase, 'CREDENTIALS_PUBLISHED')
        self.assertEqual(self.f.advance().phase, 'CREDENTIALS_PUBLISHED')
        self.assertEqual(sum(row[0] == 'promote' for row in self.f.vault.mutations), 1)

    def test_existing_intent_never_restarts_model_key_creation(self):
        self.f.base_succeeded()
        self.f.vault.add(record('creation-intent'))
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_bound_stack_without_durable_runtime_cannot_recreate(self):
        self.f.permissions_started()
        self.f.vault.rows = {1: ('unconfigured', b'UNCONFIGURED')}
        self.f.vault.pending.clear()
        writes = list(self.f.vault.mutations)
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.vault.mutations, writes)
        self.assertEqual(len(self.f.keys.created), 1)
        self.assertEqual(len(self.f.orm.jobs), 2)
