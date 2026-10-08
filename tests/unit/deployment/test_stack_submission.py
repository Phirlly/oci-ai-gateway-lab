"""Stack create-once behavior across durable intent and interrupted requests."""

import unittest

from deployment.credential_errors import DeliveryError, MutationUncertain
from deployment.stack_submission import ensure_stack
from .submission_fixtures import submission_fixture


class StackSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()

    def submit(self):
        f = self.f
        return ensure_stack(f.orm, f.journal, f.target, f.package)

    def test_fresh_stack_is_created_once_and_reused(self):
        first = self.submit()
        self.assertEqual(self.submit().stack_id, first.stack_id)
        writes = [p for name, p in self.f.orm.calls if name == 'create_stack']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['terraformVersion'], '1.5.x')
        self.assertEqual(writes[0]['workingDirectory'], 'foundation')

    def test_lost_create_reply_recovers_owned_stack(self):
        self.f.orm.fail = 'create_stack'
        with self.assertRaises(MutationUncertain):
            self.submit()
        self.f.orm.fail = None
        self.assertEqual(self.submit().state, 'ACTIVE')
        self.assertEqual(sum(c[0] == 'create_stack' for c in self.f.orm.calls), 1)

    def test_record_without_observed_stack_never_recreates(self):
        self.submit()
        self.f.orm.stacks.clear()
        with self.assertRaises(DeliveryError):
            self.submit()
        self.assertEqual(sum(c[0] == 'create_stack' for c in self.f.orm.calls), 1)

    def test_stack_without_retained_record_blocks(self):
        self.submit()
        self.f.api.rows.clear()
        with self.assertRaises(DeliveryError):
            self.submit()

    def test_wrong_source_or_working_directory_blocks_recovery(self):
        self.submit()
        self.f.orm.stacks[0]['config-source']['working-directory'] = 'other'
        with self.assertRaises(DeliveryError):
            self.submit()

    def test_registry_provider_mode_is_allowed_without_custom_provider(self):
        self.submit()
        self.f.orm.stacks[0]['is-third-party-provider-experience-enabled'] = True
        self.assertEqual(self.submit().state, 'ACTIVE')
