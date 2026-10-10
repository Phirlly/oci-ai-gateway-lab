"""Gateway responses cannot redirect credentials or bypass size/completeness limits."""

import unittest

from runtime.gateway_http import GatewayHTTP, GatewayError
from .response_server import response_server


class ResponseBoundaryContracts(unittest.TestCase):
    def setUp(self):
        url = self.enterContext(response_server())
        self.client = GatewayHTTP(url, "synthetic-session", allow_loopback=True)

    def test_redirect_is_returned_without_following_it(self):
        response = self.client.request("GET", "/redirect", timeout=1)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.body, b"")

    def test_oversized_response_fails_instead_of_accepting_truncation(self):
        with self.assertRaisesRegex(GatewayError, "size limit"):
            self.client.request("GET", "/oversized", timeout=1)

    def test_incomplete_response_fails_without_echoing_received_content(self):
        with self.assertRaises(GatewayError) as raised:
            self.client.request("GET", "/incomplete", timeout=1)
        self.assertNotIn("secret-synthetic", str(raised.exception))
