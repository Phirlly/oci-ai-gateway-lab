"""Metadata reads retain exact instance/VNIC filters and explicit signing scope."""

import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.compute_cli import ComputeCLI


class ComputeRequestContracts(unittest.TestCase):
    def test_fixed_reads_use_verified_fields_and_complete_filtered_attachment_list(self):
        requests = []

        def capture(command, **options):
            requests.append((command, options))
            output = '3.94.0' if '--version' in command else '{"data":[]}'
            return subprocess.CompletedProcess(command, 0, output, '')

        with patch('deployment.oci_cli.subprocess.run', side_effect=capture):
            client = ComputeCLI('us-ashburn-1', profile='TeamProfile')
            client.get_instance('instance')
            client.get_public_ip('public')
            client.get_private_ip('private')
            client.get_vnic('vnic')
            client.list_vnic_attachments('compartment', 'instance', 'vnic')
        expected = [
            (['compute', 'instance', 'get'], {'instanceId': 'instance'}),
            (['network', 'public-ip', 'get'], {'publicIpId': 'public'}),
            (['network', 'private-ip', 'get'], {'privateIpId': 'private'}),
            (['network', 'vnic', 'get'], {'vnicId': 'vnic'}),
            (['compute', 'vnic-attachment', 'list', '--all'],
             {'compartmentId': 'compartment', 'instanceId': 'instance', 'vnicId': 'vnic'}),
        ]
        self.assertEqual(len(requests), 6)
        for (command, options), (suffix, payload) in zip(requests[1:], expected):
            with self.subTest(suffix=suffix):
                self.assertEqual(command[command.index(suffix[0]):], suffix + ['--from-json', 'file:///dev/stdin'])
                self.assertEqual(json.loads(options['input']), payload)
                self.assertIn('TeamProfile', command)
                self.assertIn('us-ashburn-1', command)
                self.assertIn('--no-retry', command)
                self.assertTrue(options['capture_output'])
