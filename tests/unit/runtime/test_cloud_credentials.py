"""Exact CURRENT reads, bounded instance metadata and sanitized failures."""

import base64
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from runtime.cloud_credentials import current_content, instance_id
from runtime.gateway_http import GatewayError
from .bundle_fixture import INSTANCE, SETTINGS


class CloudCredentialTests(unittest.TestCase):
    def response(self, **changes):
        data = {"secret-id": SETTINGS["secret_ocid"], "stages": ["CURRENT"],
                "version-number": 1, "secret-bundle-content": {
                    "content-type": "BASE64", "content": base64.b64encode(b"UNCONFIGURED").decode()}}
        data.update(changes)
        return subprocess.CompletedProcess([], 0, json.dumps({"data": data}), "")

    def test_reads_only_configured_current_with_instance_principal(self):
        with patch("runtime.cloud_credentials.subprocess.run", return_value=self.response()) as run:
            self.assertEqual(current_content(SETTINGS), b"UNCONFIGURED")
        args, kwargs = run.call_args
        command = args[0]
        self.assertEqual(command[command.index("--auth") + 1], "instance_principal")
        self.assertEqual(command[command.index("--stage") + 1], "CURRENT")
        self.assertEqual(command[command.index("--secret-id") + 1], SETTINGS["secret_ocid"])
        self.assertEqual(command[command.index("--config-file") + 1], "/dev/null")
        self.assertIn("--no-retry", command)
        self.assertEqual(kwargs["timeout"], 45)
        self.assertFalse(any(key.startswith("OCI_") for key in kwargs["env"]))

    def test_rejects_wrong_secret_stage_and_encoding(self):
        for change in ({"secret-id": "foreign"}, {"stages": ["PENDING"]},
                       {"version-number": True}, {"secret-bundle-content": {"content-type": "BASE64", "content": "!"}}):
            with self.subTest(change=change), patch("runtime.cloud_credentials.subprocess.run", return_value=self.response(**change)):
                with self.assertRaises(GatewayError):
                    current_content(SETTINGS)

    def test_cli_error_and_timeout_never_expose_output(self):
        for effect in (subprocess.CompletedProcess([], 1, "secret text", "secret text"),
                       subprocess.TimeoutExpired("secret command", 45, output="secret text")):
            with self.subTest(effect=type(effect).__name__):
                with patch("runtime.cloud_credentials.subprocess.run", **(
                        {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect})):
                    with self.assertRaises(GatewayError) as error:
                        current_content(SETTINGS)
                self.assertNotIn("secret text", str(error.exception))

    def test_metadata_matches_instance_compartment_and_region(self):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        metadata = {"id": INSTANCE, "compartmentId": SETTINGS["compartment_ocid"],
                    "canonicalRegionName": SETTINGS["region"]}
        response.read.return_value = json.dumps(metadata).encode()
        with patch("runtime.cloud_credentials.HTTPConnection", return_value=connection) as http:
            self.assertEqual(instance_id(SETTINGS), INSTANCE)
            http.assert_called_once_with("169.254.169.254", timeout=5)
            connection.request.assert_called_once_with("GET", "/opc/v2/instance/", headers={"Authorization": "Bearer Oracle"})
            metadata["compartmentId"] = "foreign"
            response.read.return_value = json.dumps(metadata).encode()
            with self.assertRaises(GatewayError):
                instance_id(SETTINGS)
        self.assertEqual(connection.close.call_count, 2)

    def test_metadata_redirect_is_rejected(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 302
        with patch("runtime.cloud_credentials.HTTPConnection", return_value=connection):
            with self.assertRaises(GatewayError):
                instance_id(SETTINGS)
