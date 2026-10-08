"""Fixed Resource Manager read commands use the protected OCI process boundary."""

import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.resource_manager_cli import ResourceManagerCLI


class ResourceManagerRequestContracts(unittest.TestCase):
    def test_reads_use_exact_filters_all_pages_and_selected_profile(self):
        calls = []

        def capture(command, **options):
            calls.append((command, options))
            output = "3.94.0" if "--version" in command else '{"data": []}'
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch("deployment.oci_cli.subprocess.run", side_effect=capture):
            client = ResourceManagerCLI("us-ashburn-1", profile="TeamProfile")
            client.list_stacks("compartment")
            client.get_stack("stack")
            client.list_jobs("compartment", "stack")
            client.get_job("job")
        expected = [
            (["stack", "list", "--all"], {"compartmentId": "compartment"}),
            (["stack", "get"], {"stackId": "stack"}),
            (["job", "list", "--all"], {"compartmentId": "compartment", "stackId": "stack"}),
            (["job", "get"], {"jobId": "job"}),
        ]
        for (command, options), (suffix, payload) in zip(calls[1:], expected):
            with self.subTest(suffix=suffix):
                start = command.index("resource-manager")
                self.assertEqual(command[start:], ["resource-manager", *suffix, "--from-json", "file:///dev/stdin"])
                self.assertEqual(json.loads(options["input"]), payload)
                self.assertIn("TeamProfile", command)
                self.assertIn("us-ashburn-1", command)
                self.assertIn("--no-retry", command)
                self.assertNotIn("--wait-for-state", command)
                self.assertTrue(options["capture_output"])
                self.assertFalse(options["shell"])
