"""Own only one disposable Compose project's inputs and lifecycle."""

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .gateway_client import GatewayClient

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "runtime" / "compose.local.yaml"


def docker_command():
    context = os.environ.get("GATEWAY_TEST_DOCKER_CONTEXT", "default")
    return ["docker", "--context", context]


def compose_command(project):
    return docker_command() + [
        "compose", "--project-name", project, "--project-directory", str(ROOT),
        "-f", str(COMPOSE),
    ]


def run_command(command, timeout=30):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Subprocess output may include resolved configuration; do not echo it.
        raise RuntimeError(f"Container command failed (exit {result.returncode})")
    return result.stdout


class GatewayStack:
    def __init__(self):
        self.project = "gateway-contract-" + secrets.token_hex(6)
        self.directory = None
        self.previous_environment = {}
        self.started = False

    def set_environment(self, values):
        for key, value in values.items():
            if key not in self.previous_environment:
                self.previous_environment[key] = os.environ.get(key)
            os.environ[key] = value

    def __enter__(self):
        context = docker_command()[-1]
        endpoint = run_command([
            "docker", "context", "inspect", context,
            "--format", "{{.Endpoints.docker.Host}}",
        ]).strip()
        if not endpoint.startswith("unix://"):
            raise RuntimeError("Runtime contracts require a local Unix-socket context")
        try:
            return self.prepare_inputs()
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def prepare_inputs(self):
        local_temp = ROOT / ".tmp"
        local_temp.mkdir(exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix=self.project + "-", dir=local_temp))
        database_password = secrets.token_hex(24)
        master_key = "sk-" + secrets.token_hex(24)
        salt = secrets.token_hex(32)
        password_file = self.directory / "database-password"
        password_file.write_text(database_password)
        environment_file = self.directory / "gateway-secrets.json"
        environment_file.write_text(json.dumps({
            "database_password": database_password, "gateway_master_key": master_key,
            "gateway_salt_key": salt, "oci_api_key": "synthetic-unused",
            "external_api_key": "synthetic-unused",
        }))
        for path in (password_file, environment_file):
            path.chmod(0o600)
        self.set_environment({
            "GATEWAY_CONFIG_FILE": str(Path(__file__).parent / "fixtures" / "gateway.yaml"),
            "GATEWAY_SECRETS_FILE": str(environment_file),
            "DATABASE_PASSWORD_FILE": str(password_file),
            "GATEWAY_TEST_MASTER_KEY": master_key,
            "GATEWAY_TEST_PROJECT": self.project,
        })
        return self

    def start(self):
        command = self.command()
        run_command(command + ["config", "--quiet"])
        self.started = True  # Ensure cleanup even when pull/start fails.
        print("Pulling pinned runtime images...", flush=True)
        run_command(command + ["pull", "--quiet"], timeout=1200)
        print("Starting isolated runtime...", flush=True)
        run_command(command + ["up", "-d", "--wait", "--wait-timeout", "180"], timeout=240)
        port = run_command(command + ["port", "edge", "8080"]).strip()
        if not port.startswith("127.0.0.1:"):
            raise RuntimeError("Gateway was not bound to loopback")
        self.set_environment({"GATEWAY_TEST_URL": "http://" + port})
        network = self.project + "_default"
        internal = run_command(docker_command() + [
            "network", "inspect", network, "--format", "{{.Internal}}",
        ]).strip()
        if internal != "true":
            raise RuntimeError("Contract network does not enforce internal routing")
        self.wait_for_edge()

    def command(self):
        return compose_command(self.project)

    def wait_for_edge(self):
        client = GatewayClient()
        deadline = time.monotonic() + 30
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                response = client.request("GET", "/health/readiness", timeout=min(3, remaining))
                if response.status == 200 and response.json().get("db") == "connected":
                    return
            except (OSError, ValueError):
                pass
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        raise RuntimeError("Published edge did not reach gateway/database readiness")

    def __exit__(self, exc_type, exc, traceback):
        cleanup_error = None
        cleanup_complete = False
        try:
            if self.started:
                run_command(self.command() + [
                    "down", "--volumes", "--timeout", "10",
                ], timeout=90)
                label = "label=com.docker.compose.project=" + self.project
                for resource in ("container", "network", "volume"):
                    args = ["ls", "--quiet", "--filter", label]
                    if resource == "container":
                        args.append("--all")
                    if run_command(docker_command() + [resource] + args).strip():
                        raise RuntimeError(f"Owned {resource} remains after cleanup")
                print("Owned test containers, networks and volumes removed.", flush=True)
            cleanup_complete = True
        except BaseException as error:
            # Cancellation must retain the same recovery inputs as command failure.
            cleanup_error = error
        finally:
            for key, value in self.previous_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if cleanup_complete and self.directory:
                shutil.rmtree(self.directory)
        if cleanup_error:
            raise RuntimeError(
                f"Cleanup failed for {self.project}; protected inputs retained at {self.directory}"
            ) from cleanup_error
