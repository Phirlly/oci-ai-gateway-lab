"""A successful job needs captured-input and downloaded-content verification."""

import unittest

from deployment.apply_submission import ensure_apply
from deployment.credential_errors import DeliveryError, CloudReadError
from deployment.stack_submission import ensure_stack
from deployment.foundation_package import FoundationPackage
from .foundation_fixtures import archive_bytes
from .submission_fixtures import submission_fixture


class ApplyAttestationTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()
        f = self.f
        self.stack = ensure_stack(f.orm, f.journal, f.target, f.package)
        self.submit()

    def submit(self):
        f = self.f
        return ensure_apply(f.orm, f.journal, f.target, f.package, self.stack.stack_id, model_key_ocid=None)

    def test_active_job_does_not_request_archive(self):
        self.submit()
        self.assertFalse(any(c[0] == 'get_job_package' for c in self.f.orm.calls))

    def test_registry_provider_mode_is_allowed_in_job(self):
        self.f.orm.jobs[0]['is-third-party-provider-experience-enabled'] = True
        self.assertEqual(self.submit().state, 'ACCEPTED')

    def test_delayed_archive_retry_never_resubmits_job(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.fail = 'download'
        with self.assertRaises(CloudReadError):
            self.submit()
        self.f.orm.fail = None
        self.assertEqual(self.submit().state, 'SUCCEEDED')
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_wrong_captured_variables_or_workdir_cannot_attest(self):
        self.f.orm.jobs[0]['working-directory'] = 'other'
        with self.assertRaises(DeliveryError):
            self.submit()

    def test_old_success_cannot_represent_a_newer_package_submission(self):
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        newer = FoundationPackage(archive_bytes(changed='variables.tf'))
        f = self.f
        ensure_apply(f.orm, f.journal, f.target, newer, self.stack.stack_id, model_key_ocid=None)
        f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        with self.assertRaises(DeliveryError):
            self.submit()
        self.assertFalse(any(c[0] == 'get_job_package' for c in f.orm.calls))

    def test_malformed_operation_tag_stops_with_safe_error(self):
        self.f.orm.jobs[0]['freeform-tags']['operation_id'] = ['sentinel']
        with self.assertRaises(DeliveryError):
            self.submit()

    def test_unrelated_active_job_blocks(self):
        extra = dict(self.f.orm.jobs[0])
        extra['id'] += 'other'
        extra['freeform-tags'] = {}
        self.f.orm.jobs.append(extra)
        with self.assertRaises(DeliveryError):
            self.submit()
