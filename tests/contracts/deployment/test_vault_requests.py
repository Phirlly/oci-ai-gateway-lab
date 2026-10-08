"""Exact CLI payload and command contracts using synthetic captured responses."""

import base64
import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.vault_cli import VaultCLI


class VaultRequestContracts(unittest.TestCase):
    def setUp(self):
        self.requests = []

        def capture(command, **options):
            self.requests.append((command, options))
            output = "3.94.0" if "--version" in command else '{"data":[]}'
            return subprocess.CompletedProcess(command, 0, output, "")

        mocked = patch("deployment.oci_cli.subprocess.run", side_effect=capture)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.client = VaultCLI("us-ashburn-1")
        self.requests.clear()

    def request(self):
        command, options = self.requests[-1]
        return command, json.loads(options["input"]), options

    def test_pending_write_is_named_conditional_and_outside_argv(self):
        self.client.stage("secret", "runtime-operation", b"synthetic-secret", "metadata-etag")
        command, payload, options = self.request()
        self.assertIn("update-base64", command)
        self.assertEqual(payload, {
            "secretId": "secret",
            "secretContentContent": base64.b64encode(b"synthetic-secret").decode(),
            "secretContentName": "runtime-operation",
            "secretContentStage": "PENDING",
            "ifMatch": "metadata-etag",
        })
        self.assertNotIn("synthetic-secret", repr(command))
        self.assertFalse(options["shell"])
        self.assertTrue(options["capture_output"])
        self.assertTrue(options["start_new_session"])
        self.assertEqual(options["env"]["OCI_HEADER_PARSING_ERROR_MAX_RETRIES"], "0")
        for flag in ("--no-retry", "--connection-timeout", "--read-timeout", "--enable-propagation"):
            self.assertIn(flag, command)

    def test_promotion_uses_plain_update_with_no_content(self):
        self.client.promote("secret", 3, "metadata-etag")
        command, payload, _ = self.request()
        self.assertIn("update", command)
        self.assertNotIn("update-base64", command)
        self.assertEqual(payload, {
            "secretId": "secret", "currentVersionNumber": 3, "ifMatch": "metadata-etag"
        })

    def test_version_discovery_requests_every_page(self):
        self.client.versions("secret")
        command, payload, _ = self.request()
        self.assertIn("--all", command)
        self.assertEqual(payload, {"secretId": "secret"})

    def test_bundle_reads_use_exact_name_or_number(self):
        self.client.bundle("secret", version_name="runtime-operation")
        _, named, _ = self.request()
        self.assertEqual(named, {"secretId": "secret", "secretVersionName": "runtime-operation"})
        self.client.bundle("secret", version_number=3)
        _, numbered, _ = self.request()
        self.assertEqual(numbered, {"secretId": "secret", "versionNumber": 3})

    def test_ambiguous_bundle_selector_is_rejected_without_process(self):
        for selectors in ({}, {"version_number": 3, "version_name": "runtime-operation"}):
            with self.subTest(selectors=selectors):
                with self.assertRaises(ValueError):
                    self.client.bundle("secret", **selectors)
        self.assertEqual(self.requests, [])
