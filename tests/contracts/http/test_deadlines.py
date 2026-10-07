"""Real local sockets must obey total deadlines even while data keeps arriving."""

import os
import signal
import time
import unittest
from unittest.mock import patch

from tests.contracts.runtime.gateway_client import GatewayClient
from .response_server import response_server


class RequestDeadlineContracts(unittest.TestCase):
    def setUp(self):
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        url = self.enterContext(response_server())
        self.enterContext(patch.dict(os.environ, {"GATEWAY_TEST_URL": url}))
        self.client = GatewayClient()

    def tearDown(self):
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertEqual(signal.getsignal(signal.SIGALRM), self.previous_handler)

    def assert_total_deadline(self, path):
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            self.client.request("GET", path, timeout=0.25)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_trickling_headers_cannot_extend_total_budget(self):
        self.assert_total_deadline("/slow-headers")

    def test_trickling_body_cannot_extend_total_budget(self):
        self.assert_total_deadline("/slow-body")

    def test_normal_response_keeps_status_and_body(self):
        response = self.client.request("GET", "/normal", timeout=1)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_http_error_keeps_status_and_body(self):
        response = self.client.request("GET", "/denied", timeout=1)
        self.assertEqual(response.status, 403)
        self.assertEqual(response.json(), {"ok": True})
