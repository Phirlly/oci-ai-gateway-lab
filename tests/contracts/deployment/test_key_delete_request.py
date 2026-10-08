"""Deletion alone uses a bounded exact-resource waiter; no body is required."""

import json
import subprocess
import unittest
from unittest.mock import patch

from deployment.credential_errors import MutationUncertain
from deployment.model_keys_cli import ModelKeysCLI


class KeyDeleteRequestContracts(unittest.TestCase):
    def test_delete_accepts_no_content_only_after_bounded_waiter_success(self):
        calls = []

        def capture(command, **options):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, '3.94.0' if '--version' in command else '', '')

        with patch('deployment.oci_cli.subprocess.run', side_effect=capture):
            client = ModelKeysCLI('us-ashburn-1')
            self.assertIsNone(client.delete('key', 'etag'))
        command, options = calls[1]
        self.assertEqual(command[command.index('generative-ai'):], [
            'generative-ai', 'api-key', 'delete', '--force', '--wait-for-state', 'DELETED',
            '--max-wait-seconds', '20', '--wait-interval-seconds', '2', '--from-json', 'file:///dev/stdin',
        ])
        self.assertEqual(json.loads(options['input']), {'apiKeyId': 'key', 'ifMatch': 'etag'})
        self.assertIn('--no-retry', command)
        self.assertEqual(options['timeout'], 30)

    def test_waiter_timeout_and_service_error_never_report_success_or_raw_output(self):
        for code in (1, 2):
            def failed(command, **options):
                if '--version' in command:
                    return subprocess.CompletedProcess(command, 0, '3.94.0', '')
                return subprocess.CompletedProcess(command, code, 'sentinel', 'sentinel')
            with self.subTest(code=code), patch('deployment.oci_cli.subprocess.run', side_effect=failed):
                client = ModelKeysCLI('us-ashburn-1')
                with self.assertRaises(MutationUncertain) as error:
                    client.delete('key', 'etag')
                self.assertNotIn('sentinel', str(error.exception))
