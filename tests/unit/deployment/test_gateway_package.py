"""Complete packages contain portable runtime assets and preserve legacy archives."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from deployment.credential_errors import DeliveryError
from deployment.foundation_package import FoundationPackage, GatewayPackage, GATEWAY_FILES, MEMBERS


class GatewayPackageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for source in GATEWAY_FILES.values():
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic " + source)

    def test_explicit_full_manifest_excludes_other_files(self):
        (self.root / "runtime/private.env").write_text("excluded-sentinel")
        package = GatewayPackage.build(self.root)
        self.assertTrue(package.is_gateway)
        self.assertNotIn(b"excluded-sentinel", package.content)
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            self.assertEqual(set(archive.namelist()), set(GATEWAY_FILES))
        self.assertEqual(FoundationPackage(package.content).digest, package.digest)

    def test_original_foundation_build_keeps_its_eight_member_format(self):
        package = FoundationPackage.build(self.root / "infra")
        self.assertFalse(package.is_gateway)
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            self.assertEqual(set(archive.namelist()), MEMBERS)

    def test_missing_runtime_and_symlinked_source_directory_fail(self):
        source = self.root / "runtime/bootstrap.py"
        source.unlink()
        with self.assertRaises(DeliveryError):
            GatewayPackage.build(self.root)
        source.write_text("restored")
        (self.root / "runtime").rename(self.root / "other")
        (self.root / "runtime").symlink_to(self.root / "other", target_is_directory=True)
        with self.assertRaises(DeliveryError):
            GatewayPackage.build(self.root)

    def test_partial_full_archive_is_rejected(self):
        package = GatewayPackage.build(self.root)
        changed = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(package.content)) as source, zipfile.ZipFile(changed, "w") as target:
            for name in source.namelist():
                if name != "runtime/bootstrap.py":
                    target.writestr(name, source.read(name))
        with self.assertRaises(DeliveryError):
            FoundationPackage(changed.getvalue())
