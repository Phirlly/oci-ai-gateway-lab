"""Dependency resume and sanitized, bounded subprocess failures."""

import subprocess
import unittest
from unittest.mock import patch

from runtime.gateway_http import GatewayError
from runtime.host_commands import ensure_dependencies, start_services


def result(output="", code=0):
    return subprocess.CompletedProcess([], code, output, "private subprocess output")


class HostCommandTests(unittest.TestCase):
    installed = ("docker.io=29.1.3-0ubuntu3~24.04.2:installed\n"
                 "docker-compose-v2=2.40.3+ds1-0ubuntu1~24.04.1:installed\n"
                 "python3-venv=3.12.3:installed\niptables=1.8.10:installed\nca-certificates=20240203:installed\n")
    def test_installed_pins_skip_network_installation(self):
        with patch("runtime.host_commands.subprocess.run", side_effect=[
                result("python3-venv=3.12.3:installed\niptables=1.8.10:installed\nca-certificates=20240203:installed\n"
                       "docker-compose-v2=2.40.3+ds1-0ubuntu1~24.04.1:installed\n"
                       "docker.io=29.1.3-0ubuntu3~24.04.2:installed\n"), result("3.94.0\n")]) as run:
            ensure_dependencies()
        self.assertEqual(run.call_count, 2)

    def test_missing_venv_or_unconfigured_package_reenters_package_recovery(self):
        for python_status in ("", "python3-venv=3.12.3:unpacked\n"):
            installed = ("docker.io=29.1.3-0ubuntu3~24.04.2:installed\n"
                         "docker-compose-v2=2.40.3+ds1-0ubuntu1~24.04.1:installed\n"
                         "iptables=1.8.10:installed\nca-certificates=20240203:installed\n" + python_status)
            with self.subTest(status=python_status), patch("runtime.host_commands.subprocess.run", side_effect=[
                    result(installed), result(), result(code=1)]) as run:
                with self.assertRaises(GatewayError):
                    ensure_dependencies()
                self.assertTrue(any("--configure" in call.args[0] for call in run.call_args_list))

    def test_missing_dependencies_reach_apt_repair_and_are_revalidated(self):
        with patch("runtime.host_commands.subprocess.run", side_effect=[
                result(code=1), result(code=1), result(), result(), result(self.installed), result("3.94.0\n")]) as run:
            ensure_dependencies()
        repair = next(call.args[0] for call in run.call_args_list if "install" in call.args[0])
        self.assertIn("--fix-broken", repair)
        self.assertIn("--no-remove", repair)
        self.assertEqual(sum("/usr/bin/dpkg-query" in call.args[0] for call in run.call_args_list), 2)

    def test_incomplete_repair_stops_before_cli_install(self):
        with patch("runtime.host_commands.subprocess.run", side_effect=[
                result(code=1), result(), result(), result(), result(code=1)]) as run:
            with self.assertRaises(GatewayError):
                ensure_dependencies()
        self.assertFalse(any("pip" in call.args[0] for call in run.call_args_list))

    def test_package_failure_stops_before_python_install(self):
        with patch("runtime.host_commands.subprocess.run", side_effect=[result(code=1), result(), result(code=1)]) as run:
            with self.assertRaises(GatewayError) as error:
                ensure_dependencies()
        self.assertNotIn("private subprocess output", str(error.exception))
        self.assertFalse(any("pip" in call.args[0] for call in run.call_args_list))

    def test_pull_timeout_does_not_attempt_start(self):
        with patch("runtime.host_commands.subprocess.run", side_effect=subprocess.TimeoutExpired("private", 600)) as run:
            with self.assertRaises(GatewayError) as error:
                start_services()
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("private", str(error.exception))
