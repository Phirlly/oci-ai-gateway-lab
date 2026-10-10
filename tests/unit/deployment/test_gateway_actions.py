"""Four actions preserve secret requirements, readiness truth and bounded side effects."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from deployment.gateway_actions import GatewayActions
from deployment.gateway_observation import GatewayObservation
from deployment.credential_errors import DeliveryError
from deployment.gateway_config import GatewayConfig
from deployment.resource_manager_stacks import StackTarget
from .gateway_config_fixture import GATEWAY_SETTINGS, CONTEXT
from runtime.gateway_http import GatewayError
from demo.verification import PresenterUnavailable


class GatewayActionTests(unittest.TestCase):
    def setUp(self):
        self.orm, self.journal, self.compute = Mock(), Mock(), Mock()
        self.journal.read.return_value = []
        target = StackTarget(GatewayConfig(GATEWAY_SETTINGS), 'a' * 64)
        self.actions = GatewayActions(self.orm, self.journal, target, Mock(is_gateway=True), self.compute,
                                      vault=Mock(), keys=Mock())

    def test_status_needs_no_provider_password_or_model_request(self):
        with patch('deployment.gateway_actions.observe_gateway', return_value=GatewayObservation('DEPLOYED', context=CONTEXT)), \
             patch('deployment.gateway_actions.check_health') as health, \
             patch('deployment.gateway_actions.verify_demo') as verify:
            result = self.actions.status()
        self.assertFalse(result['ready'])
        self.assertEqual(result['verification'], 'NOT_RUN')
        self.assertEqual(result['health'], 'PASS')
        self.assertIn('/ui/playground/?tab=compare', result['compare_url'])
        health.assert_called_once()
        verify.assert_not_called()

    def test_deploy_rejects_missing_initial_key_or_bad_password_before_cloud_writes(self):
        for key, password in ((None, 'Synthetic9!password'), ('synthetic', 'bad')):
            with self.subTest(key=key), patch('deployment.gateway_actions.advance_handoff') as advance:
                with self.assertRaises(DeliveryError):
                    self.actions.deploy(key, password)
                advance.assert_not_called()

    def test_deploy_verifies_once_only_after_publication_and_presenter_ready(self):
        progress = SimpleNamespace(phase='CREDENTIALS_PUBLISHED', runtime_context=CONTEXT)
        report = {'ready': True, 'samples': [{'status': 'PASS'}]}
        with patch('deployment.gateway_actions.advance_handoff', return_value=progress), \
             patch.object(self.actions, '_wait_frontend') as wait, \
             patch('deployment.gateway_actions.verify_demo', return_value=report) as verify:
            result = self.actions.deploy('synthetic-key', 'Synthetic9!password')
        self.assertTrue(result['ready'])
        self.assertEqual(result['status'], 'Ready')
        wait.assert_called_once()
        verify.assert_called_once()

    def test_failed_model_report_never_becomes_ready_or_gets_retried(self):
        observation = GatewayObservation('DEPLOYED', context=CONTEXT)
        with patch('deployment.gateway_actions.observe_gateway', return_value=observation), \
             patch('deployment.gateway_actions.verify_demo', return_value={'ready': False, 'samples': []}) as verify:
            result = self.actions.verify('current-password')
        self.assertFalse(result['ready'])
        self.assertEqual(result['status'], 'Verification failed')
        verify.assert_called_once()

    def test_verify_unfinished_deployment_does_not_call_models(self):
        with patch('deployment.gateway_actions.observe_gateway', return_value=GatewayObservation('APPLY_FAILED')), \
             patch('deployment.gateway_actions.verify_demo') as verify:
            with self.assertRaises(DeliveryError):
                self.actions.verify('current-password')
        verify.assert_not_called()

    def test_login_health_and_tls_failure_keep_known_deployment_result(self):
        observation = GatewayObservation('DEPLOYED', context=CONTEXT)
        for error in (PresenterUnavailable('Presenter login failed'), GatewayError('Gateway unavailable'), TimeoutError()):
            with self.subTest(error=type(error).__name__), \
                 patch('deployment.gateway_actions.observe_gateway', return_value=observation), \
                 patch('deployment.gateway_actions.verify_demo', side_effect=error) as verify:
                result = self.actions.verify('current-password')
            self.assertFalse(result['ready'])
            self.assertEqual(result['status'], 'Deployed; not ready')
            self.assertEqual(result['verification'], 'FAILED')
            self.assertIn(CONTEXT['public_ip'], result['compare_url'])
            self.assertEqual(result['username'], GATEWAY_SETTINGS['presenter_email'])
            self.assertTrue(result['error'])
            verify.assert_called_once()

    def test_frontend_timeout_keeps_url_without_starting_model_calls(self):
        from deployment.action_wait import PollTimeout
        progress = SimpleNamespace(phase='CREDENTIALS_PUBLISHED', runtime_context=CONTEXT)
        with patch('deployment.gateway_actions.advance_handoff', return_value=progress), \
             patch.object(self.actions, '_wait_frontend', side_effect=PollTimeout('Timed out')), \
             patch('deployment.gateway_actions.verify_demo') as verify:
            result = self.actions.deploy('synthetic-key', 'Synthetic9!password')
        self.assertFalse(result['ready'])
        self.assertIn(CONTEXT['public_ip'], result['compare_url'])
        self.assertEqual(result['verification'], 'FAILED')
        verify.assert_not_called()

    def test_ownership_failure_still_stops_instead_of_becoming_readiness_failure(self):
        with patch('deployment.gateway_actions.advance_handoff', side_effect=DeliveryError('Ownership conflict')):
            with self.assertRaisesRegex(DeliveryError, 'Ownership'):
                self.actions.deploy('synthetic-key', 'Synthetic9!password')

    def test_remove_uses_no_runtime_or_presenter_and_requires_empty_managed_state(self):
        progress = SimpleNamespace(phase='DESTROY', job=SimpleNamespace(state='SUCCEEDED', job_id='job'))
        self.orm.get_job_state.return_value = b'{"version":4,"resources":[]}'
        with patch('deployment.gateway_actions.advance_removal', return_value=progress), \
             patch('deployment.gateway_actions.verify_demo') as verify:
            result = self.actions.remove()
        self.assertEqual(result['status'], 'Removed')
        verify.assert_not_called()
        self.orm.get_job_state.assert_called_once_with('job')
