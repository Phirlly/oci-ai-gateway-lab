"""Teardown retains recovery inputs until owned-resource removal is verified."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.contracts.runtime import stack


class StackCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = patch.object(stack, "ROOT", Path(temporary.name))
        root.start()
        self.addCleanup(root.stop)
        environment = patch.dict(os.environ, {"GATEWAY_TEST_PROJECT": "caller-project"})
        environment.start()
        self.addCleanup(environment.stop)
        self.fixture = stack.GatewayStack().prepare_inputs()
        self.fixture.started = True

    def assert_recoverable_failure(self, results):
        with patch.object(stack, "run_command", side_effect=results):
            with self.assertRaises(BaseException) as raised:
                self.fixture.__exit__(None, None, None)
        self.assertTrue((self.fixture.directory / "gateway.env").is_file())
        self.assertTrue((self.fixture.directory / "database-password").is_file())
        self.assertEqual(os.environ["GATEWAY_TEST_PROJECT"], "caller-project")
        self.assertIsInstance(raised.exception, RuntimeError)
        self.assertIn(self.fixture.project, str(raised.exception))
        self.assertIn(str(self.fixture.directory), str(raised.exception))

    def test_interrupted_down_retains_inputs_and_reports_recovery(self):
        self.assert_recoverable_failure([KeyboardInterrupt()])

    def test_interrupted_verification_retains_inputs_and_reports_recovery(self):
        self.assert_recoverable_failure(["", "", KeyboardInterrupt()])

    def test_command_failure_retains_inputs_and_reports_recovery(self):
        self.assert_recoverable_failure([RuntimeError("synthetic container failure")])

    def test_remaining_owned_resource_retains_inputs_and_reports_recovery(self):
        self.assert_recoverable_failure(["", "owned-container"])

    def test_confirmed_cleanup_removes_inputs_and_restores_environment(self):
        with patch.object(stack, "run_command", return_value="") as command:
            self.fixture.__exit__(None, None, None)
        self.assertEqual(command.call_count, 4)
        self.assertFalse(self.fixture.directory.exists())
        self.assertEqual(os.environ["GATEWAY_TEST_PROJECT"], "caller-project")
