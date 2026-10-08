"""Narrow OCI CLI 3.94.0 adapter for Vault content operations on POSIX."""

import base64
import json
import math
import os
import subprocess

from .credential_errors import DeliveryError, MutationUncertain, VaultReadError

_ENVIRONMENT_KEYS = {
    "HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
}
_COMMANDS = {
    "metadata": ("vault", "secret", "get"),
    "versions": ("vault", "secret-version", "list", "--all"),
    "bundle": ("secrets", "secret-bundle", "get"),
    "stage": ("vault", "secret", "update-base64", "--force"),
    "promote": ("vault", "secret", "update", "--force"),
}


class VaultCLI:
    def __init__(self, region, *, profile="DEFAULT", config_file=None,
                 command=("oci",), timeout=30):
        if os.name != "posix":
            raise DeliveryError("Credential delivery requires Linux or macOS.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise DeliveryError("CLI timeout must be a finite positive number.")
        if not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise DeliveryError("CLI timeout must be between zero and 300 seconds.")
        self.timeout = timeout
        self.environment = {
            key: value for key, value in os.environ.items() if key in _ENVIRONMENT_KEYS
        }
        self.environment["OCI_HEADER_PARSING_ERROR_MAX_RETRIES"] = "0"
        self.command = list(command) + [
            "--cli-rc-file", "/dev/null", "--profile", profile,
            "--region", region, "--auth", "api_key", "--output", "json",
            "--query", "@", "--no-retry", "--enable-propagation", "False",
            "--connection-timeout", "5", "--read-timeout", "20",
        ]
        if config_file is not None:
            self.command += ["--config-file", str(config_file)]
        version = self._execute(self.command + ["--version"], "", mutation=False)
        if version.strip() != "3.94.0":
            raise DeliveryError("Credential delivery requires OCI CLI 3.94.0.")

    def _execute(self, command, content, *, mutation):
        error = MutationUncertain if mutation else VaultReadError
        try:
            result = subprocess.run(
                command, input=content, capture_output=True, text=True,
                encoding="utf-8", timeout=self.timeout, shell=False,
                start_new_session=True, env=self.environment,
            )
            if result.returncode or len(result.stdout) > 1048576:
                raise error("Vault operation could not be verified; reconcile before retry.")
            return result.stdout
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            raise error("Vault operation could not be verified; reconcile before retry.") from None

    def _request(self, operation, payload):
        mutation = operation in {"stage", "promote"}
        output = self._execute(
            self.command + list(_COMMANDS[operation]) + [
                "--from-json", "file:///dev/stdin",
            ],
            json.dumps(payload, ensure_ascii=False),
            mutation=mutation,
        )
        try:
            result = json.loads(output)
            if not isinstance(result, dict) or "data" not in result:
                raise ValueError("Response shape")
            return result
        except (ValueError, RecursionError):
            error = MutationUncertain if mutation else VaultReadError
            raise error("Vault response could not be verified; reconcile before retry.") from None

    def metadata(self, secret_id):
        return self._request("metadata", {"secretId": secret_id})

    def versions(self, secret_id):
        return self._request("versions", {"secretId": secret_id})

    def bundle(self, secret_id, *, version_number=None, version_name=None):
        if (version_number is None) == (version_name is None):
            raise ValueError("Select exactly one secret version name or number.")
        selector = (
            {"versionNumber": version_number} if version_number is not None
            else {"secretVersionName": version_name}
        )
        return self._request("bundle", {"secretId": secret_id, **selector})

    def stage(self, secret_id, version_name, content, etag):
        return self._request("stage", {
            "secretId": secret_id,
            "secretContentContent": base64.b64encode(content).decode("ascii"),
            "secretContentName": version_name,
            "secretContentStage": "PENDING",
            "ifMatch": etag,
        })

    def promote(self, secret_id, version_number, etag):
        return self._request("promote", {
            "secretId": secret_id, "currentVersionNumber": version_number,
            "ifMatch": etag,
        })
