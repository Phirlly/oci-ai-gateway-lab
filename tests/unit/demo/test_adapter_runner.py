"""Adapter assertions retain their exit status, deadline and scoped cleanup."""

import unittest
from unittest.mock import Mock, patch

from tests.contracts.demo import __main__ as runner


class AdapterRunnerTests(unittest.TestCase):
    def test_assertion_failure_is_returned_after_cleanup(self):
        fixture = Mock()
        fixture.__enter__ = Mock(return_value=fixture)
        fixture.__exit__ = Mock(return_value=False)
        fixture.run_contracts.return_value = 1
        with patch.object(runner, 'ProviderStack', return_value=fixture):
            self.assertEqual(runner.main(), 1)
        fixture.start.assert_called_once()
        fixture.run_contracts.assert_called_once()
        fixture.__exit__.assert_called_once()

    def test_container_exec_is_bounded_and_propagates_nonzero_status(self):
        from tests.contracts.demo.stack import ProviderStack
        stack = ProviderStack()
        with patch('tests.contracts.demo.stack.subprocess.run', return_value=Mock(returncode=1)) as run:
            self.assertEqual(stack.run_contracts(), 1)
        args, options = run.call_args
        self.assertEqual(args[0][-6:], ['exec', '-T', 'gateway', 'python3', '-m', 'tests.contracts.demo.in_container'])
        self.assertEqual(options['timeout'], 900)
