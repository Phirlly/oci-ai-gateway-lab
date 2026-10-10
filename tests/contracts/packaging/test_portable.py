"""Extract each supported package outside the checkout and validate with Terraform1.5.7."""

import io
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from deployment.foundation_package import FoundationPackage, GatewayPackage

ROOT = Path(__file__).resolve().parents[3]


class PortablePackageContracts(unittest.TestCase):
    def terraform(self, directory, *arguments):
        binary = os.environ.get("GATEWAY_TERRAFORM_15", str(ROOT / ".cache/terraform/1.5.7/terraform"))
        result = subprocess.run([binary, "-chdir=" + str(directory), *arguments],
                                capture_output=True, text=True, timeout=180,
                                env={**os.environ, "TF_IN_AUTOMATION": "1", "TF_INPUT": "0"})
        self.assertEqual(result.returncode, 0, "Portable Terraform command failed: " + arguments[0])
        return result.stdout

    def test_legacy_and_gateway_archives_are_self_contained(self):
        for package in (FoundationPackage.build(ROOT / "infra"), GatewayPackage.build(ROOT)):
            with self.subTest(gateway=package.is_gateway), tempfile.TemporaryDirectory(prefix="gateway-package-") as directory:
                extracted = Path(directory)
                with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
                    archive.extractall(extracted)  # Constructor already checked the exact member allowlist.
                foundation = extracted / "foundation"
                version = self.terraform(foundation, "version")
                self.assertIn("Terraform v1.5.7", version)
                self.terraform(foundation, "init", "-backend=false", "-input=false", "-lockfile=readonly",
                               "-plugin-dir=" + str(ROOT / "infra/.terraform/providers"))
                self.terraform(foundation, "validate", "-no-color")
                if package.is_gateway:
                    for path in (extracted / "runtime").glob("*.py"):
                        compile(path.read_text(), path.name, "exec")
                self.assertFalse((extracted / "docs").exists())
                self.assertFalse((extracted / "deployment.tfvars.json").exists())
