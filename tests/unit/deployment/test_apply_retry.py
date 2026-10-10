"""Only a confirmed failed Apply can consume the single recovery attempt."""

import unittest
from copy import deepcopy

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from deployment.foundation_history import recover_base
from deployment.stack_submission import ensure_stack
from .submission_fixtures import submission_fixture


class ApplyRetryTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)
        self.original = self.apply()

    def apply(self, retry=False):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id,
                            model_key_ocid=None, retry_failed=retry)

    def test_failed_original_gets_one_retry_with_identical_inputs(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.f.orm.stacks[0]['freeform-tags']['operator'] = 'preserved'
        variables = deepcopy(self.f.orm.stacks[0]['variables'])
        retry = self.apply(True)
        self.assertNotEqual(retry.job_id, self.original.job_id)
        self.assertEqual(retry.state, 'ACCEPTED')
        self.assertEqual(self.f.orm.jobs[1]['variables'], variables)
        self.assertEqual(self.f.orm.stacks[0]['freeform-tags']['operator'], 'preserved')
        self.assertEqual(self.apply().job_id, retry.job_id)
        self.f.orm.jobs[1]['lifecycle-state'] = 'FAILED'
        self.assertEqual(self.apply(True).state, 'FAILED')
        self.assertEqual(len(self.f.orm.jobs), 2)
        self.assertEqual(sum(c[0] == 'create_stack' for c in self.f.orm.calls), 1)

    def test_active_canceled_successful_and_default_failed_do_not_retry(self):
        for state in ('ACCEPTED', 'IN_PROGRESS', 'CANCELING', 'CANCELED', 'SUCCEEDED'):
            self.f.orm.jobs[0]['lifecycle-state'] = state
            with self.subTest(state=state):
                self.assertEqual(self.apply(True).job_id, self.original.job_id)
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.assertEqual(self.apply().state, 'FAILED')
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_successful_retry_supplies_base_identity_without_more_writes(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        retry = self.apply(True)
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        f = self.f
        _, base = recover_base(f.orm, f.journal, f.target, f.package, self.stack.stack_id)
        self.assertEqual(base.job_id, retry.job_id)
        self.assertIn(('get_job_package', retry.job_id), f.orm.calls)
        self.assertEqual(self.apply(True).job_id, retry.job_id)
        self.assertEqual(len(f.orm.jobs), 2)

    def test_changed_predecessor_state_invalidates_retry_history(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.apply(True)
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        with self.assertRaises(DeliveryError):
            self.apply()
        self.assertEqual(len(self.f.orm.jobs), 2)

    def test_superseded_request_and_nonboolean_retry_stop_before_mutation(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.f.orm.stacks[0]['freeform-tags']['request_hash'] = '0' * 64
        with self.assertRaises(DeliveryError):
            self.apply(True)
        with self.assertRaises(DeliveryError):
            self.apply('yes')
        self.assertEqual(len(self.f.orm.jobs), 1)
