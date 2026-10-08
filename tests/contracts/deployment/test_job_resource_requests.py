"""Job inventory stays on the protected read-only OCI command boundary."""

import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.resource_manager_cli import ResourceManagerCLI


class JobResourceRequestContracts(unittest.TestCase):
    def test_exact_job_compartment_all_pages_without_mutation_flags(self):
        calls = []

        def capture(command, **options):
            calls.append((command, options))
            output = '3.94.0' if '--version' in command else '{"data":{"items":[]}}'
            return subprocess.CompletedProcess(command, 0, output, '')

        with patch('deployment.oci_cli.subprocess.run', side_effect=capture):
            client = ResourceManagerCLI('us-ashburn-1', profile='TeamProfile')
            result = client.list_job_resources('job', 'compartment')
        self.assertEqual(result, {'data': {'items': []}})
        self.assertEqual(len(calls), 2)
        command, options = calls[1]
        self.assertEqual(command[command.index('resource-manager'):], [
            'resource-manager', 'associated-resource-summary',
            'list-job-associated-resources', '--all', '--from-json', 'file:///dev/stdin',
        ])
        self.assertEqual(json.loads(options['input']), {'jobId': 'job', 'compartmentId': 'compartment'})
        for value in ('TeamProfile', 'us-ashburn-1', '--no-retry'):
            self.assertIn(value, command)
        for value in ('--force', '--wait-for-state'):
            self.assertNotIn(value, command)
