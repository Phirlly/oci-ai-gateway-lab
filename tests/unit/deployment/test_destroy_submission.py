"""Owned partial infrastructure can be destroyed without a successful Apply."""

import unittest

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError
from deployment.destroy_submission import ensure_destroy
from deployment.foundation_history import recover_base
from deployment.stack_submission import ensure_stack
from .destroy_fixture import destroy_fixture
from .orm_fixtures import KEY_ID


class DestroySubmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = destroy_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)

    def destroy(self):
        f = self.f
        return ensure_destroy(f.orm, f.journal, f.target, f.package, self.stack.stack_id)

    def apply(self, key=None):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id, model_key_ocid=key)

    def test_fresh_destroy_uploads_trusted_config_then_submits_exactly_once(self):
        result = self.destroy()
        self.assertEqual((result.operation, result.state), ('DESTROY', 'ACCEPTED'))
        writes = [c for c in self.f.orm.calls if c[0] in ('update_stack', 'create_destroy')]
        self.assertEqual([c[0] for c in writes], ['update_stack', 'create_destroy'])
        self.assertFalse(writes[1][1]['jobOperationDetailsIsProviderUpgradeRequired'])
        self.assertEqual(writes[1][1]['executionPlanStrategy'], 'AUTO_APPROVED')
        self.assertEqual(self.destroy(), result)
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_failed_partial_apply_does_not_require_vault_outputs_or_archive(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.f.orm.fail = 'download'
        self.assertEqual(self.destroy().operation, 'DESTROY')
        self.assertFalse(any(c[0] == 'get_job_package' for c in self.f.orm.calls))

    def test_existing_model_binding_and_unrelated_tags_are_preserved(self):
        self.apply(KEY_ID)
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.f.orm.stacks[0]['freeform-tags']['operator'] = 'preserved'
        result = self.destroy()
        self.assertEqual(result.model_key_ocid, KEY_ID)
        self.assertEqual(self.f.orm.stacks[0]['variables']['oci_model_key_ocid'], KEY_ID)
        self.assertEqual(self.f.orm.stacks[0]['freeform-tags']['operator'], 'preserved')

    def test_active_apply_or_nonactive_stack_prevents_destroy(self):
        self.apply()
        with self.assertRaises(DeliveryError):
            self.destroy()
        self.f.orm.jobs[0]['lifecycle-state'] = 'FAILED'
        self.f.orm.stacks[0]['lifecycle-state'] = 'DELETING'
        with self.assertRaises(DeliveryError):
            self.destroy()
        self.assertFalse(any(c[0] == 'create_destroy' for c in self.f.orm.calls))

    def test_apply_cannot_restart_after_destroy_intent(self):
        self.destroy()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        with self.assertRaisesRegex(DeliveryError, 'Destroy'):
            self.apply()
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_bound_credential_preparation_stops_after_destroy_intent(self):
        self.apply()
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.apply(KEY_ID)
        self.f.orm.jobs[1]['lifecycle-state'] = 'FAILED'
        self.destroy()
        f = self.f
        with self.assertRaisesRegex(DeliveryError, 'Destroy'):
            recover_base(f.orm, f.journal, f.target, f.package, self.stack.stack_id)
