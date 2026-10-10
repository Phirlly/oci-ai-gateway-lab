"""Owned cleanup reconciles both Apply attempts and prevents later restart."""

import unittest

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from deployment.destroy_submission import ensure_destroy
from deployment.stack_submission import ensure_stack
from .destroy_fixture import destroy_fixture


class RetryCleanupTests(unittest.TestCase):
    def test_destroy_after_either_retry_outcome_blocks_future_apply(self):
        for state in ('SUCCEEDED', 'FAILED', 'CANCELED'):
            with self.subTest(state=state):
                f = destroy_fixture()
                stack = ensure_stack(f.orm, f.journal, f.target, f.package)
                args = (f.orm, f.journal, f.target, f.package, stack.stack_id)
                ensure_apply(*args, model_key_ocid=None)
                f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
                ensure_apply(*args, model_key_ocid=None, retry_failed=True)
                f.orm.jobs[1]['lifecycle-state'] = state
                destroyed = ensure_destroy(*args)
                self.assertEqual(destroyed.operation, 'DESTROY')
                self.assertEqual(ensure_destroy(*args).job_id, destroyed.job_id)
                with self.assertRaises(DeliveryError):
                    ensure_apply(*args, model_key_ocid=None, retry_failed=True)
                self.assertEqual(len(f.orm.jobs), 3)
