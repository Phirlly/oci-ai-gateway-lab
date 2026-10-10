"""Only confirmed staging rejections cross the process boundary as retryable."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import traceback
import unittest
from unittest.mock import patch

from deployment.credential_errors import DeliveryError, MutationUncertain
from deployment.vault_cli import VaultCLI

FIXTURE = Path(__file__).parent / 'fixtures' / 'oci_etag_rejection.py'
SECRET = 'ocid1.vaultsecret.oc1.iad.example'
VERSION = 'runtime-' + 'a' * 32


class VaultETagTransportContracts(unittest.TestCase):
    def connection(self, mode, **options):
        return VaultCLI('us-ashburn-1', command=(sys.executable, str(FIXTURE), mode), **options)

    def test_confirmed_rejection_is_classified_without_transport_replay_or_disclosure(self):
        for mode, status, code in (('conflict', 409, 'Conflict'), ('precondition', 412, 'NoEtagMatch'),
                                   ('gzip-tag', 409, 'Conflict')):
            stdout, stderr = io.StringIO(), io.StringIO()
            tag = 'a' * 64 + '--gzip' if mode == 'gzip-tag' else 'older'
            with self.subTest(mode=mode), patch('deployment.oci_cli.subprocess.run', wraps=subprocess.run) as run:
                client = self.connection(mode)
                run.reset_mock()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(DeliveryError) as error:
                        client.stage(SECRET, VERSION, b'secret-sentinel', tag)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(json.loads(run.call_args.kwargs['input'])['ifMatch'], tag)
                self.assertEqual(type(error.exception).__name__, 'VaultETagConflict')
                self.assertNotIsInstance(error.exception, MutationUncertain)
                self.assertEqual(stdout.getvalue(), '')
                self.assertEqual(stderr.getvalue(), f'OCI service response: HTTP {status}; code {code}.\n')
                trace = ''.join(traceback.format_exception(error.exception))
                for private in ('sentinel', SECRET, tag, 'newer'):
                    self.assertNotIn(private, trace)

    def test_unconfirmed_or_timed_out_rejections_remain_uncertain(self):
        for mode in ('generic', 'wrong-secret', 'wrong-tag', 'timeout'):
            with self.subTest(mode=mode), contextlib.redirect_stderr(io.StringIO()):
                client = self.connection(mode, timeout=0.25 if mode == 'timeout' else 5)
                with self.assertRaises(MutationUncertain):
                    client.stage(SECRET, VERSION, b'secret-sentinel', 'older')

    def test_promotion_and_cleanup_do_not_gain_retry_authority(self):
        client = self.connection('conflict')
        operations = (
            lambda: client.promote(SECRET, 3, 'older'),
            lambda: client.stage(SECRET, 'cleanup-' + 'a' * 32, b'{}', 'older'),
            lambda: client.stage(SECRET, VERSION, b'{}', ''),
        )
        for operation in operations:
            with self.subTest(operation=operation), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(MutationUncertain):
                    operation()
