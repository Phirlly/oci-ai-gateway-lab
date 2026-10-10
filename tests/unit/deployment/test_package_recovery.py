"""Existing deployments keep their original package when the checkout changes."""

import unittest
from unittest.mock import Mock

from deployment.credential_errors import DeliveryError
from deployment.foundation_package import FoundationPackage
from deployment.package_recovery import deployment_package
from deployment.stack_submission import ensure_stack
from .foundation_fixtures import archive_bytes
from .submission_fixtures import submission_fixture


class PackageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = submission_fixture()
        self.f.orm.get_stack_package = Mock(return_value=self.f.package.content)
        self.build = Mock(return_value=FoundationPackage(archive_bytes(changed="identity.tf")))

    def recover(self):
        return deployment_package(self.f.orm, self.f.journal, self.f.target, self.build)

    def test_new_scope_builds_current_package_once_without_cloud_writes(self):
        selected = self.recover()
        self.assertEqual(selected, self.build.return_value)
        self.build.assert_called_once_with()
        self.assertEqual(self.f.orm.stacks, [])

    def test_created_stack_before_first_apply_recovers_original_archive(self):
        ensure_stack(self.f.orm, self.f.journal, self.f.target, self.f.package)
        self.assertEqual(self.recover().digest, self.f.package.digest)
        self.build.assert_not_called()
        self.assertEqual(self.f.orm.jobs, [])

    def test_changed_stack_archive_fails_instead_of_using_local_checkout(self):
        ensure_stack(self.f.orm, self.f.journal, self.f.target, self.f.package)
        self.f.orm.get_stack_package.return_value = archive_bytes(changed="identity.tf")
        with self.assertRaises(DeliveryError):
            self.recover()
        self.build.assert_not_called()

    def test_missing_recorded_stack_does_not_build_a_new_deployment(self):
        ensure_stack(self.f.orm, self.f.journal, self.f.target, self.f.package)
        self.f.orm.stacks.clear()
        with self.assertRaises(DeliveryError):
            self.recover()
        self.build.assert_not_called()
