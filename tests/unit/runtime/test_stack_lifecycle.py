"""Interrupted fixture preparation must remove inputs and restore the caller."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.contracts.runtime import stack


class StackLifecycleTests(unittest.TestCase):
    def test_interrupted_entry_removes_credentials_and_restores_environment(self):
        original_prepare = stack.GatewayStack.prepare_inputs

        def interrupted_prepare(instance):
            original_prepare(instance)
            raise KeyboardInterrupt

        original_project = os.environ.get("GATEWAY_TEST_PROJECT")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(stack, "ROOT", Path(directory)):
                with patch.object(stack, "run_command", return_value="unix:///local.sock"):
                    with patch.object(stack.GatewayStack, "prepare_inputs", interrupted_prepare):
                        fixture = stack.GatewayStack()
                        with self.assertRaises(KeyboardInterrupt):
                            with fixture:
                                self.fail("Interrupted setup must not enter the test body")
                        self.assertFalse(fixture.directory.exists())
        self.assertEqual(os.environ.get("GATEWAY_TEST_PROJECT"), original_project)
