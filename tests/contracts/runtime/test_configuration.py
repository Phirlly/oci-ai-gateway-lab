"""Rendered Compose contracts: required inputs, isolation and scoped storage."""

import json
import os
import subprocess
import unittest

from .stack import compose_command


class ConfigurationContracts(unittest.TestCase):
    def test_missing_config_input_fails_before_startup(self):
        environment = dict(os.environ)
        environment.pop("GATEWAY_CONFIG_FILE", None)
        result = subprocess.run(
            compose_command("gateway-config-contract") + ["config", "--quiet"],
            env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATEWAY_CONFIG_FILE", result.stderr)

    def test_profile_publishes_only_edge_and_isolates_backends(self):
        result = subprocess.run(
            compose_command("gateway-config-contract") + ["config", "--format", "json"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        config = json.loads(result.stdout)
        services = config["services"]
        self.assertEqual(services["gateway"]["entrypoint"], ["python3", "-m", "runtime.gateway_entrypoint"])
        self.assertNotIn("DATABASE_URL", services["gateway"]["environment"])
        self.assertNotIn("LITELLM_MASTER_KEY", services["gateway"]["environment"])
        for name in ("gateway", "database"):
            self.assertFalse("ports" in services[name], f"{name} must not publish ports")
            self.assertEqual(set(services[name]["networks"]), {"default"})
        self.assertEqual(set(services["edge"]["networks"]), {"default", "frontend"})
        self.assertEqual(services["edge"]["ports"][0]["host_ip"], "127.0.0.1")
        self.assertEqual(len(services["edge"]["ports"]), 1)
        self.assertTrue(config["networks"]["default"]["internal"])
        self.assertFalse(config["networks"]["frontend"].get("internal", False))
        self.assertFalse(config["networks"]["frontend"].get("external", False))
        self.assertNotIn("external", config["volumes"]["postgres_data"])
