"""Fixed HTTPS requests protect tokens and enforce real socket deadlines."""

import http.client
import signal
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from deployment.credential_errors import DeliveryError, MutationUncertain
from deployment.github_http import GitHubHTTP
from tests.contracts.http.response_server import response_server


class GitHubHTTPContracts(unittest.TestCase):
    def test_explicit_host_headers_and_no_redirect_or_retry(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 302
        response.getheaders.return_value = [('Location', 'https://evil.example')]
        response.read.return_value = b'raw-secret-sentinel'
        with patch('deployment.github_http.http.client.HTTPSConnection', return_value=connection) as factory:
            client = GitHubHTTP('token-sentinel')
            with self.assertRaises(MutationUncertain) as error:
                client.request('POST', '/repos/example/demo/deployments', {}, expected=201)
        self.assertNotIn('sentinel', str(error.exception))
        self.assertNotIn('token-sentinel', repr(client))
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(factory.call_args.args, ('api.github.com',))
        headers = connection.request.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer token-sentinel')
        self.assertEqual(headers['X-GitHub-Api-Version'], '2026-03-10')
        connection.close.assert_called_once()

    def test_duplicate_json_fields_are_rejected(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = []
        response.read.return_value = b'{"id":1,"id":2}'
        with patch('deployment.github_http.http.client.HTTPSConnection', return_value=connection):
            with self.assertRaises(DeliveryError):
                GitHubHTTP('synthetic').request('GET', '/repos/example/demo')

    def test_truncated_valid_json_is_not_a_complete_response(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = [('Content-Length', '100')]
        response.read.return_value = b'{"id":1}'
        with patch('deployment.github_http.http.client.HTTPSConnection', return_value=connection):
            with self.assertRaises(DeliveryError):
                GitHubHTTP('synthetic').request('GET', '/repos/example/demo')

    def test_oversized_response_is_rejected(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = []
        response.read.return_value = b' ' * (1024 * 1024 + 1)
        with patch('deployment.github_http.http.client.HTTPSConnection', return_value=connection):
            with self.assertRaises(DeliveryError):
                GitHubHTTP('synthetic').request('GET', '/repos/example/demo')

    def test_trickling_headers_and_body_obey_total_deadline(self):
        with response_server() as url:
            parsed = urlsplit(url)
            for path in ('/slow-headers', '/slow-body'):
                with self.subTest(path=path):
                    def local_connection(*args, **kwargs):
                        return http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=1)
                    with patch('deployment.github_http.http.client.HTTPSConnection', side_effect=local_connection):
                        started = time.monotonic()
                        with self.assertRaises(DeliveryError):
                            GitHubHTTP('synthetic', timeout=.2).request('GET', path)
                        self.assertLess(time.monotonic() - started, 1)
                    self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
