"""Fixed Linux dependency and Compose operations for this dedicated VM."""

import re
import subprocess

from .cloud_credentials import OCI
from .gateway_http import GatewayError

SOURCE = "/opt/oci-ai-gateway"
DOCKER_VERSION = "29.1.3-0ubuntu3~24.04.2"
COMPOSE_VERSION = "2.40.3+ds1-0ubuntu1~24.04.1"
COMPOSE = ["/usr/bin/docker", "compose", "--project-name", "oci-ai-gateway",
           "--project-directory", SOURCE, "-f", SOURCE + "/runtime/compose.cloud.yaml"]


def _run(command, phase, timeout, *, allow_failure=False):
    environment = {"HOME": "/root", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                   "LANG": "C.UTF-8", "DEBIAN_FRONTEND": "noninteractive"}
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                stdin=subprocess.DEVNULL, timeout=timeout, env=environment)
        if result.returncode and not allow_failure:
            raise GatewayError(phase + " failed; bootstrap will retry without resetting credentials")
        return result
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise GatewayError(phase + " could not complete within its time budget") from None


def _packages_installed():
    packages = ["docker.io", "docker-compose-v2", "python3-venv", "ca-certificates", "iptables"]
    installed = _run(["/usr/bin/dpkg-query", "-W", "-f=${Package}=${Version}:${db:Status-Status}\n", *packages],
                     "Package inspection", 15, allow_failure=True)
    rows = installed.stdout.splitlines()
    pins = {"docker.io=" + DOCKER_VERSION + ":installed", "docker-compose-v2=" + COMPOSE_VERSION + ":installed"}
    complete = (len(rows) == len(packages) and pins.issubset(rows)
                and all(any(re.fullmatch(name + r"=[^\s:]+(?::[^\s:]+)*:installed", row) for row in rows)
                        for name in packages[2:]))
    return installed.returncode == 0 and complete


def ensure_dependencies():
    if not _packages_installed():
        # dpkg cannot fetch missing dependencies; apt must still get a chance to repair.
        _run(["/usr/bin/dpkg", "--configure", "--pending"], "Interrupted package recovery", 120, allow_failure=True)
        options = ["/usr/bin/apt-get", "-o", "DPkg::Lock::Timeout=60", "-o", "Acquire::Retries=2"]
        _run(options + ["update"], "Package index refresh", 180)
        _run(options + ["install", "--yes", "--no-install-recommends", "--fix-broken", "--no-remove",
                        "docker.io=" + DOCKER_VERSION, "docker-compose-v2=" + COMPOSE_VERSION,
                        "python3-venv", "ca-certificates", "iptables"], "Pinned host package installation", 360)
        if not _packages_installed():
            raise GatewayError("Required host packages remain incomplete after repair")
    try:
        version = _run([OCI, "--version"], "OCI CLI inspection", 15, allow_failure=True)
    except GatewayError:
        version = None
    if version is None or version.returncode or version.stdout.strip() != "3.94.0":
        _run(["/usr/bin/python3", "-m", "venv", SOURCE + "/oci-cli"], "OCI CLI environment setup", 60)
        _run([SOURCE + "/oci-cli/bin/python", "-m", "pip", "install", "--disable-pip-version-check",
              "--no-input", "oci-cli==3.94.0"], "Pinned OCI CLI installation", 300)
        if _run([OCI, "--version"], "OCI CLI verification", 15).stdout.strip() != "3.94.0":
            raise GatewayError("Installed OCI CLI version does not match the deployment")


def start_services():
    _run(COMPOSE + ["pull", "--quiet"], "Pinned container download", 600)
    _run(COMPOSE + ["up", "-d", "--wait", "--wait-timeout", "180"], "Gateway startup", 240)


def stop_bootstrap_timer():
    _run(["/usr/bin/systemctl", "disable", "--now", "oci-ai-gateway-bootstrap.timer"],
         "Completed bootstrap timer shutdown", 30)
