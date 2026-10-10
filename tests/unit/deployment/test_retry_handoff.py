"""Recovered foundation jobs preserve staged credentials and publication gates."""

import unittest

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from .foundation_fixtures import archive_bytes
from .handoff_fixture import HandoffFixture
from .record_fixtures import EXPIRES


class RetryHandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = HandoffFixture()

    def retry(self, result):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, result.stack_id,
                            model_key_ocid=result.job.model_key_ocid, retry_failed=True)

    def test_pending_base_retry_cannot_create_credentials(self):
        first = self.f.advance()
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.retry(first)
        for state in ('ACCEPTED', 'FAILED', 'CANCELED'):
            self.f.orm.jobs[1]['lifecycle-state'] = state
            with self.subTest(state=state):
                self.assertEqual(self.f.advance().job.state, state)
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(self.f.vault.mutations, [])
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        result = self.f.advance(external_api_key='external', demo_password='password', expires_at=EXPIRES)
        self.assertEqual(result.phase, 'PERMISSIONS')
        self.assertEqual(len(self.f.keys.created), 1)

    def test_permission_retry_reuses_key_and_bundle_until_attested_success(self):
        original = self.f.permissions_started()
        rows = dict(self.f.vault.rows)
        self.f.orm.jobs[1]['lifecycle-state'] = 'FAILED'
        retry = self.retry(original)
        pending = self.f.advance()
        self.assertEqual(pending.job.job_id, retry.job_id)
        self.assertEqual(pending.credentials, original.credentials)
        self.assertEqual(self.f.vault.rows, rows)
        self.assertEqual(self.f.vault.current, 1)
        self.f.orm.jobs[2]['lifecycle-state'] = 'SUCCEEDED'
        result = self.f.advance()
        self.assertEqual(result.phase, 'CREDENTIALS_PUBLISHED')
        self.assertEqual(self.f.vault.rows, rows)
        self.assertEqual(len(self.f.keys.created), 1)
        self.assertEqual(len(self.f.orm.jobs), 3)

    def test_mismatched_successful_retry_archive_blocks_publication(self):
        original = self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'FAILED'
        retry = self.retry(original)
        self.f.orm.jobs[2]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.archives[retry.job_id] = archive_bytes(changed='variables.tf')
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.vault.current, 1)
