"""Real child-process checks with a synthetic executable, no OCI access."""

import contextlib
import io
import os
import sys
import time
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment.credential_errors import DeliveryError, MutationUncertain, VaultReadError
from deployment.vault_cli import VaultCLI

FIXTURE = Path(__file__).parent / "fixtures" / "oci_process.py"


def client(mode="echo", **options):
    return VaultCLI(
        "us-ashburn-1", command=(sys.executable, str(FIXTURE), mode), **options
    )


class CliProcessContracts(unittest.TestCase):
    def test_named_profile_custom_config_and_secrets_use_explicit_channels(self):
        connection = client(profile="DemoProfile", config_file="/protected/connection")
        result = connection.stage("secret-id", "runtime-operation", b"secret-sentinel", "etag")
        data = result["data"]
        self.assertEqual(data["request"]["secretContentStage"], "PENDING")
        self.assertIn("DemoProfile", data["argv"])
        self.assertIn("/protected/connection", data["argv"])
        self.assertIn("file:///dev/stdin", data["argv"])
        self.assertNotIn("secret-sentinel", str(data["argv"]))

    def test_default_profile_and_controlled_environment_ignore_ambient_overrides(self):
        dangerous = {
            "OCI_CLI_PROFILE": "foreign", "OCI_CLI_KEY_CONTENT": "secret-sentinel",
            "OCI_CLI_DEBUG": "true", "OCI_CLI_METRICS_PATH": "/unwanted",
            "PYTHONPATH": "/untrusted", "OCI_PYSDK_PROPAGATION_REQUEST_ID_FILE": "/unwanted",
        }
        with patch.dict(os.environ, dangerous):
            data = client().metadata("secret-id")["data"]
        self.assertIn("DEFAULT", data["argv"])
        self.assertIn("/dev/null", data["argv"])
        self.assertFalse(set(dangerous) & set(data["environment_keys"]))
        self.assertIn("OCI_HEADER_PARSING_ERROR_MAX_RETRIES", data["environment_keys"])

    def test_mutation_failure_and_contaminated_stdout_are_sanitized(self):
        for mode in ("failure", "contaminated"):
            with self.subTest(mode=mode):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(MutationUncertain) as error:
                        client(mode).promote("secret-id", 3, "etag")
                formatted = "".join(traceback.format_exception(error.exception))
                self.assertNotIn("secret-sentinel", formatted)
                self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_read_failure_remains_a_read_error(self):
        with patch("deployment.vault_cli.time.sleep") as sleep:
            with self.assertRaises(VaultReadError):
                client("failure").metadata("secret-id")
        sleep.assert_not_called()

    def test_process_deadline_captures_partial_secret_output(self):
        connection = client("timeout", timeout=0.25)
        started = time.monotonic()
        with self.assertRaises(MutationUncertain) as error:
            connection.promote("secret-id", 3, "etag")
        self.assertLess(time.monotonic() - started, 2)
        self.assertNotIn("secret-sentinel", "".join(traceback.format_exception(error.exception)))

    def test_unsupported_cli_version_is_rejected_before_api_operation(self):
        with self.assertRaisesRegex(DeliveryError, "3.94.0"):
            client("old-version")
