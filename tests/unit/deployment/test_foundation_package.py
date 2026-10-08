"""Foundation packaging includes only reviewed Terraform inputs."""

import tempfile
import os
import unittest
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

from deployment.credential_errors import DeliveryError
from deployment.foundation_package import FoundationPackage, SOURCE_FILES


class FoundationPackageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in SOURCE_FILES:
            (self.root / name).write_text('# synthetic ' + name)

    def test_package_excludes_settings_state_docs_and_tests(self):
        for name in ('.env', 'deployment.tfvars.json', 'terraform.tfstate'):
            (self.root / name).write_text('excluded-sentinel')
        package = FoundationPackage.build(self.root)
        with ZipFile(BytesIO(package.content)) as archive:
            self.assertEqual(set(archive.namelist()), {'foundation/' + n for n in SOURCE_FILES})
        self.assertNotIn(b'excluded-sentinel', package.content)
        self.assertEqual(package.content, FoundationPackage.build(self.root).content)

    def test_missing_required_source_is_rejected(self):
        (self.root / 'providers.tf').unlink()
        with self.assertRaises(DeliveryError):
            FoundationPackage.build(self.root)

    def test_source_symlink_is_rejected(self):
        (self.root / 'providers.tf').unlink()
        (self.root / 'providers.tf').symlink_to(self.root / 'versions.tf')
        with self.assertRaises(DeliveryError):
            FoundationPackage.build(self.root)

    def test_nonregular_source_is_rejected_without_waiting_for_input(self):
        (self.root / 'providers.tf').unlink()
        os.mkfifo(self.root / 'providers.tf')
        with self.assertRaises(DeliveryError):
            FoundationPackage.build(self.root)

    def test_owned_temporary_zip_is_removed_on_failure(self):
        package = FoundationPackage.build(self.root)
        with self.assertRaises(RuntimeError):
            with package.path() as path:
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                raise RuntimeError('synthetic')
        self.assertFalse(path.exists())
