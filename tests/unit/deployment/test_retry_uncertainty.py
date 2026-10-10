"""Lost replies and unavailable evidence never grant another Apply attempt."""

import unittest
from copy import deepcopy

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError, MutationUncertain
from deployment.foundation_package import FoundationPackage
from deployment.stack_submission import ensure_stack
from .foundation_fixtures import archive_bytes
from .submission_fixtures import submission_fixture


class RetryUncertaintyTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)
        ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id, model_key_ocid=None)
        f.orm.jobs[0]['lifecycle-state'] = 'FAILED'

    def retry(self):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id,
                            model_key_ocid=None, retry_failed=True)

    def test_missing_or_changed_archive_stops_before_retry_record(self):
        for unavailable in (True, False):
            self.f.orm.fail = 'download' if unavailable else None
            if not unavailable:
                self.f.orm.package = FoundationPackage(archive_bytes(changed='variables.tf'))
            with self.subTest(unavailable=unavailable), self.assertRaises(DeliveryError):
                self.retry()
        self.assertEqual(len(self.f.api.rows), 2)
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_lost_create_reply_recovers_the_same_retry(self):
        self.f.orm.fail = 'create_apply'
        with self.assertRaises(MutationUncertain):
            self.retry()
        self.f.orm.fail = None
        observed = self.retry()
        self.assertEqual(observed.job_id, self.f.orm.jobs[1]['id'])
        self.assertEqual(len(self.f.orm.jobs), 2)

    def test_lost_upload_reply_cannot_replay_retry_callback(self):
        self.f.orm.fail = 'update_stack'
        with self.assertRaises(MutationUncertain):
            self.retry()
        self.f.orm.fail = None
        with self.assertRaises(DeliveryError):
            self.retry()
        self.assertEqual(len(self.f.orm.jobs), 1)
        self.assertEqual(len(self.f.api.rows), 3)

    def test_lost_journal_reply_cannot_submit_or_replay(self):
        self.f.api.lose_create_reply = True
        with self.assertRaises(MutationUncertain):
            self.retry()
        self.f.api.lose_create_reply = False
        with self.assertRaises(DeliveryError):
            self.retry()
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_unrelated_active_job_blocks_new_attempt(self):
        unrelated = deepcopy(self.f.orm.jobs[0])
        unrelated.update({'id': unrelated['id'] + 'other', 'freeform-tags': {},
                          'lifecycle-state': 'ACCEPTED'})
        self.f.orm.jobs.append(unrelated)
        with self.assertRaises(DeliveryError):
            self.retry()
        self.assertEqual(len(self.f.api.rows), 2)
