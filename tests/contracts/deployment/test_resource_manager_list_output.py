"""Empty list rendering is allowed only for successful, fixed ORM list reads."""

import subprocess
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment.credential_errors import CloudReadError, DeliveryError
from deployment.resource_manager_cli import ResourceManagerCLI

FIXTURE = Path(__file__).parent / "fixtures" / "oci_process.py"


class ResourceManagerListOutputContracts(unittest.TestCase):
    def client(self, mode):
        return ResourceManagerCLI("us-ashburn-1", timeout=0.25,
                                  command=(sys.executable, str(FIXTURE), mode))

    def test_zero_exit_empty_stdout_is_an_empty_list_only_for_list_reads(self):
        connection = self.client("empty-list")
        self.assertEqual(connection.list_stacks("compartment"), {"data": []})
        self.assertEqual(connection.list_jobs("compartment", "stack"), {"data": []})
        with self.assertRaises(CloudReadError):
            connection.get_stack("stack")

    def test_explicit_zero_total_header_is_a_supported_empty_result(self):
        self.assertEqual(self.client("zero-total").list_stacks("compartment"), {"data": []})

    def test_error_partial_and_debug_output_never_become_absence(self):
        for mode in ("failure", "timeout", "contaminated"):
            with self.subTest(mode=mode), self.assertRaises(CloudReadError) as error:
                self.client(mode).list_stacks("compartment")
            self.assertNotIn("secret-sentinel", "".join(traceback.format_exception(error.exception)))

    def test_malformed_or_incomplete_list_envelopes_are_rejected(self):
        outputs = [
            "{}", '{"data": {}}', '{"data": null}', '{"message": "secret-sentinel"}',
            '{"opc-total-items": 2}', '{"opc-total-items": false}', '{"etag": "v"}',
            '{"data": [], "opc-next-page": "more"}', '{"data": [], "opc-next-cursor": "more"}',
            '{"data":',
        ]
        for output in outputs:
            with self.subTest(output=output):
                with patch("deployment.oci_cli.subprocess.run") as run:
                    run.side_effect = [
                        subprocess.CompletedProcess([], 0, "3.94.0", ""),
                        subprocess.CompletedProcess([], 0, output, ""),
                    ]
                    with self.assertRaises(CloudReadError):
                        ResourceManagerCLI("us-ashburn-1").list_stacks("compartment")

    def test_empty_list_mode_cannot_be_used_for_mutations(self):
        connection = self.client("empty-list")
        with patch("deployment.oci_cli.subprocess.run") as run:
            with self.assertRaises(DeliveryError):
                connection.request(("invalid",), {}, mutation=True, empty_list=True)
            run.assert_not_called()
