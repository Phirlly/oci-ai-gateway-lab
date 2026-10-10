"""The IMDS deny is idempotent, fail-closed and never flushes OCI rules."""

import subprocess
import unittest
from unittest.mock import patch

from runtime.gateway_http import GatewayError
from runtime.host_firewall import protect_metadata


class HostFirewallTests(unittest.TestCase):
    def test_installs_and_verifies_missing_rule(self):
        results = [subprocess.CompletedProcess([], code, "", "") for code in (0, 1, 0, 0)]
        with patch("runtime.host_firewall.subprocess.run", side_effect=results) as run:
            protect_metadata()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([next(value for value in cmd if value in ("-S", "-C", "-I")) for cmd in commands], ["-S", "-C", "-I", "-C"])
        inserted = commands[2]
        self.assertEqual(inserted[inserted.index("-I") + 1:inserted.index("-I") + 3], ["PREROUTING", "1"])
        self.assertIn("169.254.169.254/32", inserted)
        self.assertEqual(inserted[-2:], ["-j", "DROP"])
        for cmd in commands:
            self.assertNotIn("-F", cmd)
            self.assertNotIn("OUTPUT", cmd)
            self.assertEqual(cmd[1:5], ["-w", "5", "-t", "raw"])

    def test_existing_rule_is_not_duplicated(self):
        with patch("runtime.host_firewall.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            protect_metadata()
        self.assertEqual(run.call_count, 2)

    def test_command_failure_is_not_treated_as_absence(self):
        results = [subprocess.CompletedProcess([], code, "sensitive", "sensitive") for code in (0, 2)]
        with patch("runtime.host_firewall.subprocess.run", side_effect=results) as run:
            with self.assertRaises(GatewayError) as error:
                protect_metadata()
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("sensitive", str(error.exception))

    def test_failed_verification_stops_startup(self):
        results = [subprocess.CompletedProcess([], code, "", "") for code in (0, 1, 0, 1)]
        with patch("runtime.host_firewall.subprocess.run", side_effect=results):
            with self.assertRaises(GatewayError):
                protect_metadata()
