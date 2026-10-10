"""Load a restricted secret file, then preserve the pinned LiteLLM entrypoint."""

import json
import os
import stat
import sys
from urllib.parse import quote

from .gateway_http import GatewayError

FIELDS = {"oci_api_key", "external_api_key", "database_password", "gateway_master_key", "gateway_salt_key"}
ENTRYPOINT = "/app/docker/prod_entrypoint.sh"


def entry_environment(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 16384:
                raise ValueError
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError
        values = json.loads(raw)
        if (not isinstance(values, dict) or set(values) != FIELDS
                or any(not isinstance(value, str) or not value
                       or any(ord(c) < 32 or ord(c) == 127 for c in value)
                       for value in values.values())):
            raise ValueError
        return {
            "LITELLM_MASTER_KEY": values["gateway_master_key"],
            "LITELLM_SALT_KEY": values["gateway_salt_key"],
            "OCI_GENAI_API_KEY": values["oci_api_key"],
            "ANTHROPIC_API_KEY": values["external_api_key"],
            "DATABASE_URL": "postgresql://gateway:" + quote(values["database_password"], safe="")
                            + "@database:5432/gateway",
        }
    except (OSError, ValueError, TypeError, RecursionError):
        raise GatewayError("Gateway secret file is invalid or inaccessible") from None


def main():
    try:
        environment = dict(os.environ)
        environment.pop("DEMO_PASSWORD", None)
        environment.update(entry_environment("/run/secrets/gateway.json"))
        os.execve(ENTRYPOINT, [ENTRYPOINT, *sys.argv[1:]], environment)
    except (GatewayError, OSError):
        print("Gateway startup failed: secret inputs or pinned entrypoint unavailable", file=sys.stderr)
        return 78


if __name__ == "__main__":
    sys.exit(main())
