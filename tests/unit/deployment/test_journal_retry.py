"""A retry needs its own confirmed record, never replayed submission authority."""

import unittest
from unittest.mock import patch

from deployment.credential_errors import DeliveryError, MutationUncertain
from .journal_fixtures import JournalAPI, journal


class JournalRetryTests(unittest.TestCase):
    def setUp(self):
        self.api = JournalAPI()
        self.journal = journal(self.api)
        self.args = ('d' * 64, 'apply', 'b' * 64, 'e' * 64)
        self.original = self.journal.submit(*self.args, lambda intent: intent)

    def retry(self, callback):
        return self.journal.submit(*self.args, callback, retry_of=self.original.operation_id)

    def test_one_confirmed_retry_preserves_original_record(self):
        saved = self.original.payload()
        retry = self.retry(lambda intent: intent)
        self.assertEqual(retry.retry_of, self.original.operation_id)
        self.assertEqual(self.api.rows[0]['payload'], saved)
        self.assertEqual(self.journal.read(self.args[0]), [self.original, retry])
        with self.assertRaises(DeliveryError):
            self.retry(lambda intent: self.fail('third attempt'))
        self.assertEqual(len(self.api.rows), 2)

    def test_retry_requires_the_original_same_input_parent(self):
        for scope, kind, request, package, parent in (
            ('f' * 64, 'apply', 'b' * 64, 'e' * 64, self.original.operation_id),
            (*self.args, 'f' * 32),
            ('d' * 64, 'destroy', 'b' * 64, 'e' * 64, self.original.operation_id),
            ('d' * 64, 'apply', 'f' * 64, 'e' * 64, self.original.operation_id),
            ('d' * 64, 'apply', 'b' * 64, 'f' * 64, self.original.operation_id),
        ):
            with self.subTest(kind=kind, request=request), self.assertRaises(DeliveryError):
                self.journal.submit(scope, kind, request, package,
                                    lambda intent: self.fail('invalid parent'), retry_of=parent)
        self.assertEqual(len(self.api.rows), 1)

    def test_lost_retry_reply_never_authorizes_callback(self):
        self.api.lose_create_reply = True
        with self.assertRaises(MutationUncertain):
            self.retry(lambda intent: self.fail('uncertain authority'))
        self.api.lose_create_reply = False
        with self.assertRaises(DeliveryError):
            self.retry(lambda intent: self.fail('replayed authority'))
        self.assertEqual(len(self.api.rows), 2)

    def test_orphan_retry_in_retained_history_blocks_discovery(self):
        self.retry(lambda intent: None)
        self.api.rows.pop(0)
        with self.assertRaises(DeliveryError):
            self.journal.read(self.args[0])

    def test_retry_readback_mismatch_cannot_authorize_callback(self):
        request = self.api.request

        def changed(method, path, body=None, *, expected=200):
            data, headers = request(method, path, body, expected=expected)
            if method == 'GET' and path.endswith('/deployments/2'):
                data['payload']['retry_of'] = 'f' * 32
            return data, headers

        with patch.object(self.api, 'request', side_effect=changed):
            with self.assertRaises(MutationUncertain):
                self.retry(lambda intent: self.fail('unverified retry'))
        self.assertEqual(len(self.api.rows), 2)
