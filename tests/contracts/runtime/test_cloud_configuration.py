"""Cloud service isolation and pinned Caddy configuration, without cloud access."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.runtime_files import runtime_files
from .stack import ROOT, docker_command, run_command


class CloudConfigurationContracts(unittest.TestCase):
    def test_only_edge_is_public_and_services_receive_scoped_files(self):
        command = docker_command() + ["compose", "--project-name", "cloud-config-contract",
                                     "-f", str(ROOT / "runtime/compose.cloud.yaml"),
                                     "config", "--format", "json"]
        config = json.loads(run_command(command))
        services = config["services"]
        self.assertEqual({row["published"] for row in services["edge"]["ports"]}, {"80", "443"})
        self.assertEqual(services["gateway"]["ports"][0]["host_ip"], "127.0.0.1")
        self.assertNotIn("ports", services["database"])
        self.assertEqual(set(services["database"]["networks"]), {"database"})
        self.assertTrue(config["networks"]["database"]["internal"])
        self.assertEqual(set(services["gateway"]["networks"]), {"database", "frontend"})
        self.assertEqual(set(services["edge"]["networks"]), {"frontend"})
        self.assertEqual(services["gateway"]["entrypoint"], ["python3", "-m", "runtime.gateway_entrypoint"])
        for name, service in services.items():
            self.assertEqual(service["restart"], "unless-stopped")
            self.assertNotIn("privileged", service)
            self.assertNotIn("env_file", service)
            mounts = [row for row in service.get("volumes", []) if row["type"] == "bind"]
            self.assertTrue(all(row["read_only"] for row in mounts))
            self.assertFalse(any("docker.sock" in row["source"] for row in mounts))
            secret_targets = {row["target"] for row in mounts if "/secrets/" in row["target"]}
            expected = {"gateway": {"/run/secrets/gateway.json"},
                        "database": {"/run/secrets/database_password"}, "edge": set()}
            self.assertEqual(secret_targets, expected[name])

    def test_pinned_caddy_accepts_explicit_shortlived_ip_issuer(self):
        settings = {"model_id": "synthetic-model", "inference_region": "us-ashburn-1",
                    "external_model_id": "synthetic-external"}
        bundle = SimpleNamespace(settings=settings, public_ip="8.8.4.4",
                                 credentials={"database_password": "synthetic"})
        image = "docker.io/library/caddy@sha256:f2a1290d0463aad60660d4ec134943f183ee2a5f6c3eb7bf32dd984f2f020772"
        # A cold runner needs the image before the short, network-free adapt check.
        run_command(docker_command() + ['pull', '--quiet', image], timeout=1200)
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            path = Path(directory) / "Caddyfile"
            path.write_text(runtime_files(bundle)["Caddyfile"])
            config = json.loads(run_command(docker_command() + [
                "run", "--rm", "--pull", "never", "--network", "none", "--entrypoint", "caddy",
                "--mount", f"type=bind,source={path},target=/etc/caddy/Caddyfile,readonly",
                image,
                "adapt", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], timeout=30))
        issuer = config["apps"]["tls"]["automation"]["policies"][0]["issuers"][0]
        self.assertEqual(issuer["module"], "acme")
        self.assertEqual(issuer["profile"], "shortlived")
        self.assertEqual(issuer["ca"], "https://acme-v02.api.letsencrypt.org/directory")
