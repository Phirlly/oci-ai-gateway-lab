"""Host-only, bounded IMDS identity and instance-principal CURRENT bundle reads."""

import base64
import json
import os
import re
import subprocess
from http.client import HTTPConnection, HTTPException

from .gateway_http import GatewayError, request_deadline
from .runtime_bundle import validate_settings

OCI = "/opt/oci-ai-gateway/oci-cli/bin/oci"


def instance_id(settings):
    settings = validate_settings(settings)
    connection = HTTPConnection("169.254.169.254", timeout=5)
    try:
        with request_deadline(10):
            connection.request("GET", "/opc/v2/instance/", headers={"Authorization": "Bearer Oracle"})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError
            content = response.read(65537)
            if len(content) > 65536:
                raise ValueError
            value = json.loads(content)
            identifier = value["id"]
            if (not isinstance(identifier, str) or len(identifier) > 512
                    or re.fullmatch(r"ocid1\.instance\.oc1\.[a-z0-9-]+\.[a-zA-Z0-9._-]+", identifier) is None
                    or value["compartmentId"] != settings["compartment_ocid"]
                    or value["canonicalRegionName"] != settings["region"]):
                raise ValueError
            return identifier
    except (OSError, HTTPException, ValueError, TypeError, KeyError, RecursionError):
        raise GatewayError("Host instance identity could not be verified") from None
    finally:
        connection.close()


def current_content(settings):
    settings = validate_settings(settings)
    command = [OCI, "--config-file", "/dev/null", "--cli-rc-file", "/dev/null",
               "--auth", "instance_principal", "--region", settings["region"],
               "--output", "json", "--query", "@", "--no-retry",
               "--enable-propagation", "False", "--connection-timeout", "5", "--read-timeout", "20",
               "secrets", "secret-bundle", "get", "--secret-id", settings["secret_ocid"], "--stage", "CURRENT"]
    environment = {key: value for key, value in os.environ.items()
                   if key in {"HOME", "PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                timeout=45, env=environment, stdin=subprocess.DEVNULL)
        if result.returncode or len(result.stdout) > 65536:
            raise ValueError
        data = json.loads(result.stdout)["data"]
        if (data["secret-id"] != settings["secret_ocid"] or not isinstance(data["stages"], list)
                or "CURRENT" not in data["stages"] or type(data["version-number"]) is not int
                or data["version-number"] < 1 or data["secret-bundle-content"]["content-type"] != "BASE64"):
            raise ValueError
        content = base64.b64decode(data["secret-bundle-content"]["content"], validate=True)
        if len(content) > 16384:
            raise ValueError
        return content
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError, RecursionError):
        raise GatewayError("CURRENT secret read could not be verified; check runtime IAM and publication") from None
