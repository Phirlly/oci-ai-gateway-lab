"""Fresh execution orders foundation, durable credentials, permission and publication."""

import json
import unittest

from deployment.credential_errors import DeliveryError
from deployment.stack_submission import ensure_stack
from .handoff_fixture import HandoffFixture
from .record_fixtures import EXPIRES, KEY_ID


class HandoffSequenceTests(unittest.TestCase):
    def setUp(self):
        self.f = HandoffFixture()

    def test_fresh_run_starts_only_the_base_apply(self):
        result = self.f.advance()
        self.assertEqual((result.phase, result.job.state), ('FOUNDATION', 'ACCEPTED'))
        self.assertIsNone(result.credentials)
        self.assertEqual(len(self.f.orm.jobs), 1)
        self.assertEqual(self.f.vault.mutations, [])
        self.assertEqual(self.f.keys.created, [])

    def test_creating_stack_reports_progress_then_resumes_when_active(self):
        f = self.f
        ensure_stack(f.orm, f.journal, f.target, f.package)
        f.orm.stacks[0]['lifecycle-state'] = 'CREATING'
        result = f.advance()
        self.assertEqual((result.phase, result.stack_state, result.job), ('FOUNDATION', 'CREATING', None))
        self.assertEqual(f.orm.jobs, [])
        self.assertEqual(f.vault.mutations, [])
        self.assertEqual(f.keys.created, [])
        f.orm.stacks[0]['lifecycle-state'] = 'ACTIVE'
        resumed = f.advance()
        self.assertEqual((resumed.stack_state, resumed.job.state), ('ACTIVE', 'ACCEPTED'))
        self.assertEqual(sum(call[0] == 'create_stack' for call in f.orm.calls), 1)

    def test_failed_or_deleting_stack_is_reported_without_recreation_or_apply(self):
        f = self.f
        ensure_stack(f.orm, f.journal, f.target, f.package)
        for state in ('FAILED', 'DELETING', 'DELETED'):
            f.orm.stacks[0]['lifecycle-state'] = state
            with self.subTest(state=state):
                result = f.advance()
                self.assertEqual((result.phase, result.stack_state, result.job), ('FOUNDATION', state, None))
        self.assertEqual(f.orm.jobs, [])
        self.assertEqual(sum(call[0] == 'create_stack' for call in f.orm.calls), 1)
        self.assertEqual(f.vault.mutations, [])
        self.assertEqual(f.keys.created, [])

    def test_active_or_failed_base_never_creates_credentials(self):
        self.f.advance()
        for state in ('ACCEPTED', 'IN_PROGRESS', 'CANCELING', 'FAILED', 'CANCELED'):
            self.f.orm.jobs[0]['lifecycle-state'] = state
            with self.subTest(state=state):
                result = self.f.advance()
                self.assertEqual((result.phase, result.job.state), ('FOUNDATION', state))
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(self.f.vault.mutations, [])
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_permission_apply_requires_saved_runtime_and_active_key(self):
        self.f.base_succeeded()

        def inspect_before_permission():
            self.assertEqual(self.f.vault.current, 1)
            bundle = json.loads(self.f.vault.rows[3][1])
            self.assertEqual(bundle['kind'], 'runtime-bundle')
            self.assertEqual(bundle['model_key_ocid'], KEY_ID)
            self.assertEqual(self.f.keys.gets, [KEY_ID])

        self.f.orm.before_apply = inspect_before_permission
        result = self.f.advance(external_api_key='external-sentinel', demo_password='demo-sentinel',
                                expires_at=EXPIRES)
        self.assertEqual((result.phase, result.job.state), ('PERMISSIONS', 'ACCEPTED'))
        self.assertEqual(result.credentials.phase, 'PENDING')
        self.assertEqual(self.f.orm.jobs[1]['variables']['oci_model_key_ocid'], KEY_ID)
        self.assertEqual(len(self.f.keys.created), 1)
        self.assertEqual([row[0] for row in self.f.vault.mutations], ['stage', 'stage'])
        self.assertNotIn('sentinel', repr(result))

    def test_wrong_client_regions_or_malformed_inference_region_stop_before_stack_creation(self):
        for client in ('orm', 'vault', 'keys'):
            f = HandoffFixture()
            getattr(f, client).region = 'us-phoenix-1'
            with self.subTest(client=client), self.assertRaises(DeliveryError):
                f.advance()
            self.assertEqual(f.orm.stacks, [])
            self.assertEqual(f.vault.mutations, [])
            self.assertEqual(f.keys.created, [])
        self.f.keys.region = 'bad region'
        with self.assertRaises(DeliveryError):
            self.f.advance(inference_region='bad region')
        self.assertEqual(self.f.orm.stacks, [])

    def test_initial_creation_requires_explicit_expiry_and_secret_inputs(self):
        self.f.base_succeeded()
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(self.f.vault.mutations, [])
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_inactive_key_stays_staged_until_a_later_read_confirms_active(self):
        self.f.keys.read_changes = {'lifecycle-state': 'CREATING'}
        with self.assertRaises(DeliveryError):
            self.f.permissions_started()
        self.assertEqual(len(self.f.orm.jobs), 1)
        self.assertEqual(len(self.f.vault.rows), 3)
        self.f.keys.read_changes.clear()
        self.assertEqual(self.f.advance().phase, 'PERMISSIONS')
        self.assertEqual(len(self.f.keys.created), 1)
