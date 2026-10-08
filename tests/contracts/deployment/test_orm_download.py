"""Binary job archives are bounded separately from JSON CLI responses."""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment.credential_errors import CloudReadError
from deployment.resource_manager_cli import ResourceManagerCLI

FIXTURE = Path(__file__).parent / 'fixtures' / 'orm_download.py'
JOB_ID = 'ocid1.ormjob.oc1.iad.synthetic'


class ORMDownloadContracts(unittest.TestCase):
    def client(self, mode):
        return ResourceManagerCLI('us-ashburn-1', command=(sys.executable, str(FIXTURE), mode), timeout=.4)

    def test_raw_binary_is_preserved(self):
        self.assertEqual(self.client('binary').get_job_package(JOB_ID), b'PK\x00\xffsynthetic')

    def test_timeout_oversize_and_errors_are_sanitized(self):
        for mode in ('timeout', 'large', 'failure'):
            with self.subTest(mode=mode):
                client = self.client(mode)
                start = time.monotonic()
                with self.assertRaises(CloudReadError) as error:
                    client.get_job_package(JOB_ID)
                self.assertNotIn('sentinel', str(error.exception))
                self.assertLess(time.monotonic() - start, 1.5)

    def test_oversized_identifier_is_rejected_before_process_start(self):
        client = self.client('no-input')
        with patch('deployment.resource_manager_download.subprocess.Popen') as process:
            with self.assertRaises(CloudReadError):
                client.get_job_package(JOB_ID + 'a' * 200000)
        self.assertEqual(process.call_count, 0)

    def test_child_that_ignores_small_input_cannot_extend_deadline(self):
        client = self.client('no-input')
        started = time.monotonic()
        with self.assertRaises(CloudReadError):
            client.get_job_package(JOB_ID)
        self.assertLess(time.monotonic() - started, 1)
