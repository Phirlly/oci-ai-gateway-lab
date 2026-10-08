"""One retained Destroy intent cannot become a repeated or changed deletion."""

import unittest

from deployment.credential_errors import DeliveryError, MutationUncertain
from deployment.destroy_submission import ensure_destroy
from deployment.foundation_package import FoundationPackage
from deployment.stack_submission import ensure_stack
from .destroy_fixture import destroy_fixture
from .foundation_fixtures import archive_bytes
from .orm_fixtures import KEY_ID


class DestroyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = destroy_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)

    def destroy(self, package=None):
        f = self.f
        return ensure_destroy(f.orm, f.journal, f.target, package or f.package, self.stack.stack_id)

    def test_lost_reply_recovers_exact_job_without_resubmission(self):
        self.f.orm.fail = 'create_destroy'
        with self.assertRaises(MutationUncertain):
            self.destroy()
        self.f.orm.fail = None
        self.assertEqual(self.destroy().state, 'ACCEPTED')
        self.assertEqual(sum(c[0] == 'create_destroy' for c in self.f.orm.calls), 1)

    def test_failed_or_canceled_destroy_is_reported_without_new_job(self):
        self.destroy()
        for state in ('FAILED', 'CANCELED', 'SUCCEEDED'):
            self.f.orm.jobs[0]['lifecycle-state'] = state
            with self.subTest(state=state):
                self.assertEqual(self.destroy().state, state)
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_changed_package_or_binding_cannot_create_second_destroy(self):
        self.destroy()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        with self.assertRaises(DeliveryError):
            self.destroy(FoundationPackage(archive_bytes(changed='variables.tf')))
        self.f.orm.stacks[0]['variables']['oci_model_key_ocid'] = KEY_ID
        with self.assertRaises(DeliveryError):
            self.destroy()
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_interrupted_upload_without_job_requires_recovery(self):
        self.f.orm.fail = 'update_stack'
        with self.assertRaises(MutationUncertain):
            self.destroy()
        self.f.orm.fail = None
        with self.assertRaises(DeliveryError):
            self.destroy()
        self.assertEqual(self.f.orm.jobs, [])

    def test_missing_journal_or_wrong_job_operation_cannot_be_adopted(self):
        self.destroy()
        self.f.orm.jobs[0]['operation'] = 'APPLY'
        with self.assertRaises(DeliveryError):
            self.destroy()
        self.f.orm.jobs[0]['operation'] = 'DESTROY'
        self.f.api.rows.pop()
        with self.assertRaises(DeliveryError):
            self.destroy()
