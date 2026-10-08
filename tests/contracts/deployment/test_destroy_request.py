"""Destroy is a distinct fixed OCI command with explicit execution strategy."""

import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.resource_manager_cli import ResourceManagerCLI


class DestroyRequestContracts(unittest.TestCase):
    def test_destroy_does_not_request_provider_upgrade_or_use_apply(self):
        calls = []

        def capture(command, **options):
            calls.append((command, options))
            output = '3.94.0' if '--version' in command else '{"data":{}}'
            return subprocess.CompletedProcess(command, 0, output, '')

        payload = {'stackId': 'stack', 'executionPlanStrategy': 'AUTO_APPROVED',
                   'jobOperationDetailsIsProviderUpgradeRequired': False}
        with patch('deployment.oci_cli.subprocess.run', side_effect=capture):
            client = ResourceManagerCLI('us-ashburn-1', profile='TestProfile')
            client.create_destroy(payload)
        command, options = calls[1]
        self.assertEqual(command[command.index('resource-manager'):], [
            'resource-manager', 'job', 'create-destroy-job', '--from-json', 'file:///dev/stdin',
        ])
        self.assertEqual(json.loads(options['input']), payload)
        self.assertIn('--no-retry', command)
        self.assertNotIn('--wait-for-state', command)
