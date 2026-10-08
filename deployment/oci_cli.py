"""Protected OCI CLI process transport shared by deployment service adapters."""

import json
import math
import os
import subprocess

from .credential_errors import CloudReadError, DeliveryError, MutationUncertain

_ENVIRONMENT_KEYS = {
    "HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
}


class OCICommand:
    read_error = CloudReadError

    def __init__(self, region, *, profile="DEFAULT", config_file=None,
                 command=("oci",), timeout=30):
        if os.name != "posix":
            raise DeliveryError("Deployment automation requires Linux or macOS.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise DeliveryError("CLI timeout must be a finite positive number.")
        if not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise DeliveryError("CLI timeout must be between zero and 300 seconds.")
        self.timeout = timeout
        self.region = region
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
            raise DeliveryError("Deployment automation requires OCI CLI 3.94.0.")

    def _execute(self, command, content, *, mutation):
        error = MutationUncertain if mutation else self.read_error
        try:
            result = subprocess.run(
                command, input=content, capture_output=True, text=True,
                encoding="utf-8", timeout=self.timeout, shell=False,
                start_new_session=True, env=self.environment,
            )
            if result.returncode or len(result.stdout) > 1048576:
                raise error("OCI operation could not be verified; reconcile before retry.")
            return result.stdout
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            raise error("OCI operation could not be verified; reconcile before retry.") from None

    def request(self, command, payload, *, mutation=False, empty_list=False):
        if empty_list and mutation:
            raise DeliveryError("Empty-list handling is restricted to read operations.")
        output = self._execute(
            self.command + list(command) + [
                "--from-json", "file:///dev/stdin",
            ],
            json.dumps(payload, ensure_ascii=False),
            mutation=mutation,
        )
        try:
            if empty_list and not output.strip():
                return {"data": []}
            result = json.loads(output)
            if empty_list:
                if (isinstance(result, dict) and set(result) == {"opc-total-items"}
                        and type(result["opc-total-items"]) in (str, int)
                        and str(result["opc-total-items"]) == "0"):
                    return {"data": []}
                if (not isinstance(result, dict) or not isinstance(result.get("data"), list)
                        or "opc-next-page" in result or "opc-next-cursor" in result):
                    raise ValueError("Incomplete list response")
            if not isinstance(result, dict) or "data" not in result:
                raise ValueError("Response shape")
            return result
        except (ValueError, RecursionError):
            error = MutationUncertain if mutation else self.read_error
            raise error("OCI response could not be verified; reconcile before retry.") from None
