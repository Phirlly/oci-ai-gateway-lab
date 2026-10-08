"""Historical success proves identity only within the current recorded request."""

import unittest
from copy import deepcopy

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from deployment.foundation_history import recover_base
from deployment.foundation_package import FoundationPackage
from deployment.stack_submission import ensure_stack
from .foundation_fixtures import archive_bytes
from .orm_fixtures import KEY_ID
from .submission_fixtures import submission_fixture


class FoundationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)
        self.base = self.apply(None)

    def apply(self, key):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id,
                            model_key_ocid=key)

    def recover(self):
        f = self.f
        return recover_base(f.orm, f.journal, f.target, f.package, self.stack.stack_id)

    def test_successful_base_is_attested_without_mutation(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.calls.clear()
        stack, base = self.recover()
        self.assertEqual((stack.model_key_ocid, base.job_id), (None, self.base.job_id))
        self.assertIn(('get_job_package', base.job_id), self.f.orm.calls)
        self.assertFalse(any(call[0] in ('create_stack', 'update_stack', 'create_apply')
                             for call in self.f.orm.calls))

    def test_current_permission_job_may_be_active_or_failed_without_clearing_binding(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.apply(KEY_ID)
        for state in ('ACCEPTED', 'IN_PROGRESS', 'CANCELING', 'FAILED', 'CANCELED', 'SUCCEEDED'):
            self.f.orm.jobs[1]['lifecycle-state'] = state
            with self.subTest(state=state):
                stack, base = self.recover()
                self.assertEqual((stack.model_key_ocid, base.job_id), (KEY_ID, self.base.job_id))
        self.assertEqual(len(self.f.orm.jobs), 2)

    def test_incomplete_base_never_authorizes_credentials(self):
        for state in ('ACCEPTED', 'IN_PROGRESS', 'FAILED', 'CANCELED'):
            self.f.orm.jobs[0]['lifecycle-state'] = state
            with self.subTest(state=state), self.assertRaises(DeliveryError):
                self.recover()

    def test_changed_current_tags_variables_or_inactive_stack_block(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        original = deepcopy(self.f.orm.stacks[0])
        changes = [
            ('freeform-tags', 'request_hash', 'f' * 64),
            ('freeform-tags', 'package_hash', 'f' * 64),
            ('variables', 'oci_model_key_ocid', KEY_ID),
            (None, 'lifecycle-state', 'DELETING'),
        ]
        for section, field, value in changes:
            self.f.orm.stacks[0] = deepcopy(original)
            data = self.f.orm.stacks[0] if section is None else self.f.orm.stacks[0][section]
            data[field] = value
            with self.subTest(field=field), self.assertRaises(DeliveryError):
                self.recover()

    def test_wrong_package_or_captured_job_inputs_block(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.package = FoundationPackage(archive_bytes(changed='variables.tf'))
        with self.assertRaises(DeliveryError):
            self.recover()
        self.f.orm.package = self.f.package
        self.f.orm.jobs[0]['variables']['oci_model_key_ocid'] = KEY_ID
        with self.assertRaises(DeliveryError):
            self.recover()

    def test_unrecorded_active_job_or_missing_base_evidence_blocks(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        extra = deepcopy(self.f.orm.jobs[0])
        extra.update({'id': extra['id'] + 'other', 'freeform-tags': {}, 'lifecycle-state': 'ACCEPTED'})
        self.f.orm.jobs.append(extra)
        with self.assertRaises(DeliveryError):
            self.recover()
        self.f.orm.jobs.pop()
        self.f.api.rows.pop()
        with self.assertRaises(DeliveryError):
            self.recover()
