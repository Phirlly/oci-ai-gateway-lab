"""GenAI commands retain the one-time response and use the protected transport."""

import json
import subprocess
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment.credential_errors import CloudReadError, MutationUncertain
from deployment.model_keys_cli import ModelKeysCLI

FIXTURE = Path(__file__).parent / "fixtures" / "oci_process.py"


class ModelKeyRequestContracts(unittest.TestCase):
    def test_commands_use_exact_payloads_without_waiters_or_automatic_retry(self):
        requests = []

        def capture(command, **options):
            requests.append((command, options))
            output = "3.94.0" if "--version" in command else '{"data":{}}'
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch("deployment.oci_cli.subprocess.run", side_effect=capture):
            client = ModelKeysCLI("us-chicago-1", profile="DemoProfile")
            client.create({"compartmentId": "compartment", "keyDetails": [{"keyName": "gateway"}]})
            client.get("key-ocid")
            client.list("compartment")
        created, fetched, listed = requests[1:]
        self.assertEqual(json.loads(created[1]["input"])["keyDetails"], [{"keyName": "gateway"}])
        self.assertIn("create", created[0])
        self.assertEqual(json.loads(fetched[1]["input"]), {"apiKeyId": "key-ocid"})
        self.assertIn("get", fetched[0])
        self.assertEqual(json.loads(listed[1]["input"]), {"compartmentId": "compartment"})
        self.assertIn("api-key-collection", listed[0])
        self.assertIn("list-api-keys", listed[0])
        self.assertIn("--all", listed[0])
        for command, options in requests[1:]:
            self.assertIn("us-chicago-1", command)
            self.assertIn("DemoProfile", command)
            self.assertIn("--no-retry", command)
            self.assertIn("file:///dev/stdin", command)
            self.assertNotIn("--wait-for-state", command)
            self.assertTrue(options["capture_output"])

    def test_secret_bearing_failed_create_is_sanitized_at_process_boundary(self):
        for mode in ("failure", "contaminated", "timeout"):
            with self.subTest(mode=mode):
                client = ModelKeysCLI("us-chicago-1", timeout=0.25,
                                      command=(sys.executable, str(FIXTURE), mode))
                with self.assertRaises(MutationUncertain) as error:
                    client.create({"compartmentId": "synthetic"})
                self.assertNotIn("secret-sentinel", "".join(traceback.format_exception(error.exception)))

    def test_failed_metadata_read_is_not_classified_as_a_mutation(self):
        client = ModelKeysCLI("us-chicago-1", command=(sys.executable, str(FIXTURE), "failure"))
        with self.assertRaises(CloudReadError):
            client.get("synthetic-key")
