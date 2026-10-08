"""A confirmed new journal record invokes exactly one submission callback."""

import json
import unittest

from deployment.credential_errors import DeliveryError, MutationUncertain
from .journal_fixtures import JournalAPI, SHA, journal


class GitHubJournalTests(unittest.TestCase):
    def setUp(self):
        self.api = JournalAPI()
        self.journal = journal(self.api)
        self.args = ('d' * 64, 'create-stack', 'b' * 64, 'e' * 64)

    def test_confirmed_create_and_readback_precede_single_callback(self):
        calls = []
        result = self.journal.submit(*self.args, lambda intent: calls.append(intent) or 'submitted')
        self.assertEqual(result, 'submitted')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.api.calls[-1][0:2], ('GET', '/repos/example/gateway/deployments/1'))
        request = next(call[2] for call in self.api.calls if call[0] == 'POST')
        self.assertEqual(request['ref'], SHA)
        self.assertFalse(request['auto_merge'])
        self.assertEqual(request['required_contexts'], [])
        self.assertNotIn('ocid1.', json.dumps(request))
        self.assertEqual(self.journal.read(self.args[0]), calls)

    def test_existing_record_cannot_authorize_callback(self):
        self.journal.submit(*self.args, lambda intent: None)
        with self.assertRaises(DeliveryError):
            self.journal.submit(*self.args, lambda intent: self.fail('duplicate submission'))
        self.assertEqual(sum(c[0] == 'POST' for c in self.api.calls), 1)

    def test_uncertain_write_is_recoverable_but_never_fresh(self):
        self.api.lose_create_reply = True
        with self.assertRaises(MutationUncertain):
            self.journal.submit(*self.args, lambda intent: self.fail('uncertain create'))
        self.assertEqual(len(self.journal.read(self.args[0])), 1)
        with self.assertRaises(DeliveryError):
            self.journal.submit(*self.args, lambda intent: self.fail('replayed authority'))

    def test_readback_mismatch_prevents_oci_call(self):
        self.api.change_readback = True
        with self.assertRaises(DeliveryError):
            self.journal.submit(*self.args, lambda intent: self.fail('bad readback'))

    def test_duplicate_operation_or_unknown_payload_field_blocks_discovery(self):
        self.journal.submit(*self.args, lambda intent: None)
        self.api.rows[0]['payload']['secret'] = 'sentinel'
        with self.assertRaises(DeliveryError):
            self.journal.read(self.args[0])
