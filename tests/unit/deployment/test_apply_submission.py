"""Apply submission preserves settings and reconciles every previous intent."""

import unittest

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError, MutationUncertain
from deployment.stack_submission import ensure_stack
from .orm_fixtures import KEY_ID
from .submission_fixtures import submission_fixture


class ApplySubmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)

    def submit(self, key=None):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id, model_key_ocid=key)

    def test_upload_and_readback_precede_single_apply(self):
        self.f.orm.stacks[0]['freeform-tags']['operator'] = 'preserved'
        result = self.submit()
        self.assertEqual(result.state, 'ACCEPTED')
        writes = [call for call in self.f.orm.calls if call[0] in ('update_stack', 'create_apply')]
        self.assertEqual([name for name, _ in writes], ['update_stack', 'create_apply'])
        self.assertEqual(writes[0][1]['freeformTags']['operator'], 'preserved')
        self.assertNotIn('definedTags', writes[0][1])
        self.assertEqual(self.submit().job_id, result.job_id)
        self.assertEqual(sum(c[0] == 'create_apply' for c in self.f.orm.calls), 1)

    def test_lost_apply_reply_recovers_without_resubmission(self):
        self.f.orm.fail = 'create_apply'
        with self.assertRaises(MutationUncertain):
            self.submit()
        self.f.orm.fail = None
        self.assertEqual(self.submit().state, 'ACCEPTED')
        self.assertEqual(sum(c[0] == 'create_apply' for c in self.f.orm.calls), 1)

    def test_uncertain_update_blocks_same_and_changed_request(self):
        self.f.orm.fail = 'update_stack'
        with self.assertRaises(MutationUncertain):
            self.submit()
        self.f.orm.fail = None
        for key in (None, KEY_ID):
            with self.subTest(key=key), self.assertRaises(DeliveryError):
                self.submit(key)
        self.assertFalse(self.f.orm.jobs)

    def test_binding_can_be_added_but_cannot_be_cleared_or_replaced(self):
        self.submit()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.submit(KEY_ID)
        self.assertEqual(self.f.orm.stacks[0]['variables']['oci_model_key_ocid'], KEY_ID)
        for key in (None, KEY_ID + 'different'):
            with self.subTest(key=key), self.assertRaises(DeliveryError):
                self.submit(key)

    def test_failed_job_is_reported_without_automatic_new_attempt(self):
        self.submit()
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.assertEqual(self.submit().state, 'FAILED')
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_deleted_apply_record_blocks_unrecorded_owned_job(self):
        self.submit()
        self.f.api.rows.pop()
        with self.assertRaises(DeliveryError):
            self.submit()

    def test_resume_cannot_use_old_success_after_binding_was_removed(self):
        self.submit(KEY_ID)
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        del self.f.orm.stacks[0]['variables']['oci_model_key_ocid']
        with self.assertRaises(DeliveryError):
            self.submit(KEY_ID)
