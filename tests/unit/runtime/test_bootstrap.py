"""Late publication, interrupted setup and completed bootstrap behavior."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.bootstrap import initialize
from runtime.gateway_http import GatewayError
from runtime.runtime_bundle import BundlePending
from .bundle_fixture import INSTANCE, NOW, SETTINGS, bundle
from .presenter_fixture import AccountAPI


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.api = AccountAPI()
        self.enterContext(patch("runtime.bootstrap.PresenterAPI", return_value=self.api))
        self.dependencies = self.enterContext(patch("runtime.bootstrap.ensure_dependencies"))
        self.firewall = self.enterContext(patch("runtime.bootstrap.protect_metadata"))
        self.start = self.enterContext(patch("runtime.bootstrap.start_services"))
        self.identity = self.enterContext(patch("runtime.bootstrap.instance_id", return_value=INSTANCE))
        self.content = self.enterContext(patch("runtime.bootstrap.current_content", return_value=json.dumps(bundle()).encode()))

    def initialize(self):
        initialize(SETTINGS, self.directory, now=NOW)

    def test_late_publication_starts_only_after_verified_credentials(self):
        self.content.return_value = b"UNCONFIGURED"
        with self.assertRaises(BundlePending):
            self.initialize()
        self.start.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])
        self.content.return_value = json.dumps(bundle()).encode()
        self.initialize()
        self.start.assert_called_once()
        self.assertTrue(self.api.accepted)

    def test_complete_bootstrap_does_not_poll_or_reset_changed_password(self):
        self.initialize()
        self.api.password = "Changed!9Password"
        self.content.reset_mock()
        self.dependencies.reset_mock()
        self.start.reset_mock()
        self.initialize()
        self.content.assert_not_called()
        self.dependencies.assert_not_called()
        self.start.assert_not_called()
        self.assertEqual(self.api.password, "Changed!9Password")

    def test_install_failure_is_retried_without_partial_account_creation(self):
        self.dependencies.side_effect = GatewayError("Dependency unavailable")
        with self.assertRaises(GatewayError):
            self.initialize()
        self.content.assert_not_called()
        self.assertFalse(self.api.user_exists)
        self.dependencies.side_effect = None
        self.initialize()
        self.assertTrue(self.api.accepted)

    def test_uncertain_claim_recovers_without_rewriting_runtime_files_or_password(self):
        self.api.lose_claim_reply = True
        with self.assertRaises(GatewayError):
            self.initialize()
        inode = (self.directory / "gateway-secrets.json").stat().st_ino
        self.api.lose_claim_reply = False
        self.initialize()
        self.assertEqual(self.api.calls.count("claim"), 1)
        self.assertEqual((self.directory / "gateway-secrets.json").stat().st_ino, inode)

    def test_foreign_instance_never_starts_services(self):
        self.identity.return_value = "ocid1.instance.oc1.iad.foreign"
        with self.assertRaises(GatewayError):
            self.initialize()
        self.start.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])
