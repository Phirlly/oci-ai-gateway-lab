"""Only trusted public HTTPS or explicitly selected loopback HTTP is allowed."""

import base64
import json
import unittest

from runtime.gateway_http import GatewayHTTP, GatewayError, session_key


class GatewayHTTPBoundaryTests(unittest.TestCase):
    def test_public_verification_requires_https_and_simple_public_ipv4_origin(self):
        self.assertEqual(GatewayHTTP("https://8.8.4.4").base_url, "https://8.8.4.4")
        for url in ("http://8.8.4.4", "https://127.0.0.1", "https://169.254.169.254",
                    "https://user@8.8.4.4", "https://@8.8.4.4", "https://8.8.4.4#",
                    "https://8.8.4.4?", "https://8.8.4.4?key=secret", "file:///tmp/key"):
            with self.subTest(url=url), self.assertRaises(GatewayError):
                GatewayHTTP(url)

    def test_bootstrap_loopback_opt_in_does_not_allow_remote_plaintext(self):
        GatewayHTTP("http://127.0.0.1:4000", allow_loopback=True)
        with self.assertRaises(GatewayError):
            GatewayHTTP("http://8.8.4.4", allow_loopback=True)

    def test_ui_outer_token_extraction_requires_a_bounded_nonempty_key(self):
        payload = base64.urlsafe_b64encode(json.dumps({"key": "session-synthetic"}).encode()).decode().rstrip("=")
        self.assertEqual(session_key("header." + payload + ".signature"), "session-synthetic")
        for value in ("broken", None, "a.e30.b", "a." + "a" * 65536 + ".b"):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(GatewayError):
                session_key(value)

    def test_request_path_cannot_replace_the_verified_origin(self):
        client = GatewayHTTP("https://8.8.4.4")
        for path in ("https://example.test", "//example.test", "/a\nHost: bad"):
            with self.subTest(path=path), self.assertRaises(GatewayError):
                client.request("GET", path)
