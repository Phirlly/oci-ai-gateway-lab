"""Reuse isolated runtime lifecycle with two real adapters pointed at local fixtures."""

import json
import subprocess
from types import SimpleNamespace

from runtime.runtime_files import runtime_files
from tests.contracts.runtime.stack import GatewayStack, ROOT, compose_command, run_command


class ProviderStack(GatewayStack):
    def command(self):
        return compose_command(self.project) + ["-f", str(ROOT / "tests/contracts/demo/compose.providers.yaml")]

    def prepare_inputs(self):
        super().prepare_inputs()
        settings = {"model_id": "synthetic-oci", "inference_region": "us-ashburn-1",
                    "external_model_id": "claude-sonnet-4-6"}
        bundle = SimpleNamespace(settings=settings, public_ip="8.8.4.4", credentials={"database_password": "synthetic"})
        config = json.loads(runtime_files(bundle)["gateway.json"])
        routes = config["model_list"]
        routes[0]["litellm_params"]["api_base"] = "http://provider:8080/oci/20231130/actions/v1"
        routes[1]["litellm_params"]["api_base"] = "http://provider:8080/anthropic"
        # Isolated contract network has no external breach-check service.
        config["general_settings"]["password_policy_check_breached_passwords"] = False
        path = self.directory / "gateway.json"
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        self.set_environment({"GATEWAY_CONFIG_FILE": str(path)})
        return self

    def wait_for_edge(self):
        # This suite owns adapter protocols; the runtime suite owns published ports.
        run_command(self.command() + ["exec", "-T", "gateway", "python3", "-m",
                                     "tests.contracts.demo.in_container", "--health"], timeout=30)

    def run_contracts(self):
        # Only synthetic fixture data is visible. Stream unittest's readable output
        # and preserve its failed status; the outer context always owns cleanup.
        return subprocess.run(self.command() + ["exec", "-T", "gateway", "python3", "-m",
                                                "tests.contracts.demo.in_container"], timeout=900).returncode
