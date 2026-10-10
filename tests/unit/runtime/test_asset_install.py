"""Embedded asset extraction stays within owned code and systemd paths."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.install_assets import install_assets


class AssetInstallTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_fixed_locations_and_idempotent_contents(self):
        content = json.dumps({"runtime/__init__.py": "# code\n",
                              "runtime/systemd/docker-guard.conf": "[Service]\n"}).encode()
        install_assets(content, self.root)
        path = self.root / "opt/oci-ai-gateway/runtime/__init__.py"
        inode = path.stat().st_ino
        install_assets(content, self.root)
        self.assertEqual(path.stat().st_ino, inode)
        self.assertEqual(path.read_text(), "# code\n")
        self.assertTrue((self.root / "etc/systemd/system/docker.service.d/10-gateway-guard.conf").is_file())

    def test_foreign_paths_are_rejected_before_any_writes(self):
        for path in ("runtime/../outside", "/etc/passwd", "runtime/subdir/code.py", "runtime/settings.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                install_assets(json.dumps({"runtime/bootstrap.py": "safe", path: "bad"}).encode(), self.root)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_symlink_parent_and_conflicting_file_are_preserved(self):
        (self.root / "opt").symlink_to(self.root, target_is_directory=True)
        content = json.dumps({"runtime/bootstrap.py": "code"}).encode()
        with self.assertRaises(ValueError):
            install_assets(content, self.root)
        (self.root / "opt").unlink()
        install_assets(content, self.root)
        path = self.root / "opt/oci-ai-gateway/runtime/bootstrap.py"
        path.write_text("existing")
        with self.assertRaises(ValueError):
            install_assets(content, self.root)
        self.assertEqual(path.read_text(), "existing")

    def test_interrupted_write_does_not_leave_a_conflicting_final_asset(self):
        content = json.dumps({"runtime/bootstrap.py": "complete code"}).encode()
        with patch("runtime.install_assets.os.fsync", side_effect=OSError("synthetic disk interruption")):
            with self.assertRaises(OSError):
                install_assets(content, self.root)
        path = self.root / "opt/oci-ai-gateway/runtime/bootstrap.py"
        self.assertFalse(path.exists())
        install_assets(content, self.root)
        self.assertEqual(path.read_text(), "complete code")
