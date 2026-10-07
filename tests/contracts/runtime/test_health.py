"""Gateway process/database readiness and packaged UI availability."""

import unittest

from .gateway_client import GatewayClient


class HealthContracts(unittest.TestCase):
    def test_readiness_requires_connected_database(self):
        response = GatewayClient().request("GET", "/health/readiness")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["db"], "connected")

    def test_process_liveness_is_available_without_credentials(self):
        self.assertEqual(
            GatewayClient().request("GET", "/health/liveliness").status, 200
        )

    def test_bundled_ui_page_is_served(self):
        response = GatewayClient().request("GET", "/ui/")
        self.assertEqual(response.status, 200)
        self.assertIn(b"<html", response.body.lower())
        self.assertIn(b"<script", response.body.lower())
