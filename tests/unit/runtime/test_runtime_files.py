"""Runtime rendering scopes credentials and preserves immutable initialization files."""

import json
import tempfile
import unittest
from pathlib import Path

from runtime.gateway_http import GatewayError
from runtime.runtime_bundle import load_bundle
from runtime.runtime_files import runtime_files, write_runtime_files
from .bundle_fixture import INSTANCE, NOW, SETTINGS, bundle


class RuntimeFileTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_bundle(json.dumps(bundle()).encode(), SETTINGS, INSTANCE, now=NOW)

    def test_gateway_receives_two_explicit_routes_with_bounded_retries(self):
        files = runtime_files(self.bundle)
        config = json.loads(files["gateway.json"])
        routes = config["model_list"]
        self.assertEqual([row["model_name"] for row in routes], ["oci-managed", "external-anthropic"])
        self.assertEqual(routes[0]["litellm_params"]["api_base"],
                         "https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com/20231130/actions/v1")
        self.assertEqual(routes[0]["litellm_params"]["model"], "openai/synthetic-model")
        self.assertEqual(routes[1]["litellm_params"]["model"], "anthropic/synthetic-external")
        self.assertEqual(config["router_settings"]["num_retries"], 0)
        self.assertFalse(config["general_settings"]["background_health_checks"])
        self.assertNotIn("mock_response", files["gateway.json"])

    def test_presenter_password_is_excluded_from_every_written_runtime_file(self):
        files = runtime_files(self.bundle)
        self.assertEqual(set(files), {"gateway.json", "gateway-secrets.json", "database-password", "Caddyfile"})
        for name, content in files.items():
            with self.subTest(name=name):
                self.assertNotIn(self.bundle.credentials["demo_password"], content)
        self.assertNotIn("oci_api_key", files["database-password"])
        self.assertNotIn(self.bundle.credentials["oci_api_key"], files["gateway.json"])

    def test_https_uses_public_ip_issuer_profile_and_streaming_proxy(self):
        content = runtime_files(self.bundle)["Caddyfile"]
        for expected in ("default_sni 8.8.4.4", "https://8.8.4.4", "profile shortlived",
                         "https://acme-v02.api.letsencrypt.org/directory", "flush_interval -1"):
            self.assertIn(expected, content)
        self.assertNotIn("tls internal", content)

    def test_private_files_are_reused_and_conflicting_content_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_runtime_files(root, self.bundle)
            before = {path.name: path.stat().st_ino for path in root.iterdir()}
            write_runtime_files(root, self.bundle)
            self.assertEqual(before, {path.name: path.stat().st_ino for path in root.iterdir()})
            for path in root.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path = root / "gateway-secrets.json"
            path.write_text("preserve existing content")
            with self.assertRaises(GatewayError):
                write_runtime_files(root, self.bundle)
            self.assertEqual(path.read_text(), "preserve existing content")
