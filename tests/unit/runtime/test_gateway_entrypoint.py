"""The image adapter exposes only supported environment inputs, never presenter secrets."""

import json
import tempfile
import unittest
from pathlib import Path

from runtime.gateway_entrypoint import entry_environment
from runtime.gateway_http import GatewayError
from .bundle_fixture import bundle


class GatewayEntrypointTests(unittest.TestCase):
    def test_supported_environment_uses_encoded_database_password(self):
        credentials = bundle()["credentials"]
        del credentials["demo_password"]
        credentials["database_password"] = "special@/?password"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.json"
            path.write_text(json.dumps(credentials))
            path.chmod(0o600)
            values = entry_environment(path)
        self.assertEqual(set(values), {"DATABASE_URL", "LITELLM_MASTER_KEY", "LITELLM_SALT_KEY",
                                       "OCI_GENAI_API_KEY", "ANTHROPIC_API_KEY"})
        self.assertEqual(values["DATABASE_URL"], "postgresql://gateway:special%40%2F%3Fpassword@database:5432/gateway")

    def test_unexpected_secret_fields_are_rejected_without_echoing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.json"
            path.write_text(json.dumps(bundle()["credentials"]))
            path.chmod(0o600)
            with self.assertRaises(GatewayError) as raised:
                entry_environment(path)
            self.assertNotIn("Synthetic9!Password", str(raised.exception))
