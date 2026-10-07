"""A gateway process restart must preserve the activated database account."""

import os
import subprocess
import unittest

from .account_fixture import activated_account
from .stack import compose_command


class PersistenceContracts(unittest.TestCase):
    def test_restart_preserves_account_password_and_model_access(self):
        account = activated_account()
        command = compose_command(os.environ["GATEWAY_TEST_PROJECT"])
        subprocess.run(command + ["restart", "--no-deps", "gateway"],
                       check=True, timeout=120, capture_output=True)
        subprocess.run(command + ["up", "-d", "--wait", "--wait-timeout", "120"],
                       check=True, timeout=150, capture_output=True)
        response = account.session().request("GET", "/model_group/info")
        self.assertEqual(response.status, 200)
        self.assertEqual(len(response.json()["data"]), 2)
