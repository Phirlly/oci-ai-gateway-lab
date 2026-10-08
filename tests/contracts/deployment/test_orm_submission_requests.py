"""Actual OCI process request shapes for the three permitted ORM mutations."""

import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.resource_manager_cli import ResourceManagerCLI


class ORMSubmissionRequestContracts(unittest.TestCase):
    def test_create_update_and_apply_are_noninteractive_and_never_retry(self):
        calls = []

        def capture(command, **options):
            calls.append((command, options))
            output = '3.94.0' if '--version' in command else '{"data": {}}'
            return subprocess.CompletedProcess(command, 0, output, '')

        with patch('deployment.oci_cli.subprocess.run', side_effect=capture):
            client = ResourceManagerCLI('us-ashburn-1')
            client.create_stack({'configSource': '/synthetic/foundation.zip'})
            client.update_stack({'ifMatch': 'etag', 'variables': {'selected': 'model'}})
            client.create_apply({'stackId': 'stack', 'executionPlanStrategy': 'AUTO_APPROVED'})
        commands = [['stack', 'create'], ['stack', 'update', '--force'], ['job', 'create-apply-job']]
        for (command, options), suffix in zip(calls[1:], commands):
            with self.subTest(command=suffix):
                start = command.index('resource-manager')
                self.assertEqual(command[start:], ['resource-manager', *suffix, '--from-json', 'file:///dev/stdin'])
                self.assertIn('--no-retry', command)
                self.assertNotIn('--wait-for-state', command)
                self.assertIsInstance(json.loads(options['input']), dict)
