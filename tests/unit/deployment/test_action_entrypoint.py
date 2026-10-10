"""CLI dispatch validates settings and releases protected signing files on every exit."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from deployment.action_entrypoint import _report, main
from .gateway_config_fixture import GATEWAY_SETTINGS


class ActionEntrypointTests(unittest.TestCase):
    def test_summary_shows_attempts_even_when_a_retried_sample_passes(self):
        result = {'status': 'Ready', 'ready': True, 'verification': {'samples': [
            {'model': 'oci-managed', 'sample': 'invoice', 'stream': False,
             'status': 'PASS', 'seconds': 2.5, 'attempts': 2, 'retry_wait_seconds': 2}]}}
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            destination = Path(directory) / 'summary.md'
            _report(result, {'GITHUB_STEP_SUMMARY': str(destination)})
            summary = destination.read_text()
        self.assertIn('| Model | Sample | Streaming | Result | Attempts | Seconds |', summary)
        self.assertIn('| oci-managed | invoice | False | PASS | 2 | 2.5 |', summary)

    def environment(self):
        return {'DEPLOYMENT_CONFIG': json.dumps(GATEWAY_SETTINGS), 'GITHUB_ACTIONS': 'true',
                'GITHUB_REPOSITORY': 'synthetic/gateway', 'GITHUB_REPOSITORY_ID': '17',
                'GITHUB_SHA': 'a' * 40, 'GITHUB_TOKEN': 'synthetic-token'}

    def test_status_dispatches_without_provider_or_presenter_secrets(self):
        actions = Mock()
        actions.status.return_value = {'status': 'NOT_DEPLOYED', 'ready': False, 'verification': 'NOT_RUN'}
        connection = contextlib.nullcontext(SimpleNamespace(profile='DEFAULT', config_file='private'))
        with patch('deployment.action_entrypoint.runner_connection', return_value=connection), \
             patch('deployment.action_entrypoint.create_actions', return_value=actions), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            code = main(['--action', 'Status'], self.environment())
        self.assertEqual(code, 0)
        actions.status.assert_called_once_with()
        self.assertNotIn('synthetic-token', output.getvalue())

    def test_failed_verification_returns_failure_exit_and_preserves_safe_report(self):
        actions = Mock()
        actions.verify.return_value = {'status': 'Verification failed', 'ready': False, 'verification': {'ready': False}}
        environment = self.environment() | {'DEMO_PASSWORD': 'password-sentinel'}
        with patch('deployment.action_entrypoint.runner_connection', return_value=contextlib.nullcontext(None)), \
             patch('deployment.action_entrypoint.create_actions', return_value=actions), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--action', 'Verify samples'], environment), 1)
        actions.verify.assert_called_once_with('password-sentinel')
        self.assertNotIn('password-sentinel', output.getvalue())

    def test_invalid_settings_stop_before_signing_or_service_creation(self):
        environment = self.environment() | {'DEPLOYMENT_CONFIG': '{"secret":"sentinel"}'}
        with patch('deployment.action_entrypoint.runner_connection') as connection, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--action', 'Deploy'], environment), 1)
        connection.assert_not_called()
        self.assertNotIn('sentinel', output.getvalue())

    def test_unexpected_failure_is_sanitized_and_signing_context_exits(self):
        exited = []

        @contextlib.contextmanager
        def connection(*args):
            try:
                yield None
            finally:
                exited.append(True)

        with patch('deployment.action_entrypoint.runner_connection', side_effect=connection), \
             patch('deployment.action_entrypoint.create_actions', side_effect=RuntimeError('secret-sentinel')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--action', 'Status'], self.environment()), 1)
        self.assertEqual(exited, [True])
        self.assertNotIn('secret-sentinel', output.getvalue())
