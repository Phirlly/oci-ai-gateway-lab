"""Complete journal history is required before deciding that intent is absent."""

import unittest
from copy import deepcopy
from unittest.mock import patch

from deployment.credential_errors import CloudReadError, DeliveryError
from .journal_fixtures import JournalAPI, journal


class JournalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.api = JournalAPI()
        self.journal = journal(self.api)
        self.scope = 'a' * 64
        self.journal.submit(self.scope, 'create-stack', 'b' * 64, 'c' * 64, lambda intent: None)
        self.first = deepcopy(self.api.rows[0])
        self.second = deepcopy(self.first)
        self.second['id'] = 2
        self.second['payload'].update(kind='apply', operation_id='d' * 32, request_hash='e' * 64)

    def paged(self, *, second=None, failure=False):
        original = self.api.request

        def request(method, path, body=None, *, expected=200):
            if '?' not in path:
                if path.endswith('/2'):
                    return deepcopy(self.second), {}
                return original(method, path, body, expected=expected)
            if path.endswith('page=1'):
                return [deepcopy(self.first)], {'link': '<https://api.github.com/repositories/17/deployments?task=gateway_submission&per_page=100&page=2>; rel="next"'}
            if failure:
                raise CloudReadError('Synthetic incomplete page.')
            return [deepcopy(self.second if second is None else second)], {}
        return request

    def test_later_page_and_exact_get_are_included(self):
        with patch.object(self.api, 'request', side_effect=self.paged()):
            self.assertEqual({intent.kind for intent in self.journal.read(self.scope)}, {'create-stack', 'apply'})

    def test_partial_discovery_never_authorizes_post(self):
        before = len(self.api.rows)
        with patch.object(self.api, 'request', side_effect=self.paged(failure=True)):
            with self.assertRaises(CloudReadError):
                self.journal.submit(self.scope, 'apply', 'f' * 64, 'c' * 64, lambda intent: self.fail('submitted'))
        self.assertEqual(len(self.api.rows), before)

    def test_duplicate_id_or_operation_across_pages_blocks(self):
        duplicate = deepcopy(self.second)
        duplicate['payload']['operation_id'] = self.first['payload']['operation_id']
        for row in (self.first, duplicate):
            with self.subTest(row=row['id']), patch.object(self.api, 'request', side_effect=self.paged(second=row)):
                with self.assertRaises(DeliveryError):
                    self.journal.read(self.scope)

    def test_repository_identity_mismatch_blocks_before_listing(self):
        with patch.object(self.api, 'request', return_value=({'id': 18}, {})) as request:
            with self.assertRaises(DeliveryError):
                self.journal.read(self.scope)
        self.assertEqual(request.call_count, 1)

    def test_missing_next_link_prevents_post_or_callback(self):
        original = self.api.request

        def incomplete(method, path, body=None, *, expected=200):
            if '?' in path:
                return [], {'link': '<https://api.github.com/repositories/17/deployments?task=gateway_submission&per_page=100&page=2>; rel="last"'}
            return original(method, path, body, expected=expected)

        with patch.object(self.api, 'request', side_effect=incomplete):
            with self.assertRaises(DeliveryError):
                self.journal.submit(self.scope, 'apply', 'f' * 64, 'c' * 64, lambda intent: self.fail('submitted'))
        self.assertEqual(len(self.api.rows), 1)
