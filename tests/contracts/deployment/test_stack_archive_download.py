"""Pinned stack archive command preserves raw bytes and the correct identifier."""

import sys
import unittest
from pathlib import Path

from deployment.resource_manager_cli import ResourceManagerCLI


class StackArchiveDownloadContracts(unittest.TestCase):
    def test_stack_zip_is_downloaded_with_fixed_command_and_bounded_transport(self):
        fixture = Path(__file__).parent / "fixtures" / "orm_download.py"
        client = ResourceManagerCLI("us-ashburn-1",
                                    command=(sys.executable, str(fixture), "stack"), timeout=1)
        self.assertEqual(client.get_stack_package("ocid1.ormstack.oc1.iad.synthetic"),
                         b"PK\x00\xffsynthetic")
