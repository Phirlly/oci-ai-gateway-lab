"""Real child failures retain safe diagnostics without leaking or replaying."""

import contextlib
import io
from pathlib import Path
import subprocess
import sys
import traceback
import unittest
from unittest.mock import patch

from deployment.credential_errors import MutationUncertain, VaultReadError
from deployment.vault_cli import VaultCLI

FIXTURE = Path(__file__).parent / 'fixtures' / 'oci_process.py'


class CliDiagnosticContracts(unittest.TestCase):
    def connection(self, mode, **options):
        return VaultCLI('us-ashburn-1', command=(sys.executable, str(FIXTURE), mode), **options)

    def test_failed_mutation_emits_only_fixed_summary_and_is_not_replayed(self):
        for mode, code in (('service-error', 'IncorrectState'), ('service-unknown', 'unavailable')):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(mode=mode), patch('deployment.oci_cli.subprocess.run', wraps=subprocess.run) as run:
                connection = self.connection(mode)
                run.reset_mock()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(MutationUncertain) as error:
                        connection.stage('private-secret-id', 'runtime-operation', b'secret-sentinel', 'private-etag')
                self.assertEqual(run.call_count, 1)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), f'OCI service response: HTTP 409; code {code}.\n')
            self.assertNotIn('sentinel', ''.join(traceback.format_exception(error.exception)))

    def test_read_failure_keeps_its_classification(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(VaultReadError):
            self.connection('service-error').metadata('private-secret-id')
        self.assertEqual(stderr.getvalue(), 'OCI service response: HTTP 409; code IncorrectState.\n')

    def test_partial_service_output_from_timed_out_process_remains_suppressed(self):
        stderr = io.StringIO()
        connection = self.connection('service-timeout', timeout=0.25)
        with contextlib.redirect_stderr(stderr), self.assertRaises(MutationUncertain) as error:
            connection.promote('private-secret-id', 3, 'private-etag')
        self.assertEqual(stderr.getvalue(), '')
        self.assertNotIn('sentinel', ''.join(traceback.format_exception(error.exception)))
