"""Render the two model routes and write immutable private service inputs."""

import json
import os
import stat
import tempfile
from pathlib import Path

from .gateway_http import GatewayError
from .runtime_bundle import MODEL_ALIASES


def runtime_files(bundle):
    settings = bundle.settings
    routes = [
        {"model_name": MODEL_ALIASES[0], "model_info": {"id": MODEL_ALIASES[0], "mode": "chat"},
         "litellm_params": {
             "model": "openai/" + settings["model_id"], "api_key": "os.environ/OCI_GENAI_API_KEY",
             "api_base": "https://inference.generativeai." + settings["inference_region"]
                         + ".oci.oraclecloud.com/20231130/actions/v1",
         }},
        {"model_name": MODEL_ALIASES[1], "model_info": {"id": MODEL_ALIASES[1], "mode": "chat"},
         "litellm_params": {"model": "anthropic/" + settings["external_model_id"],
                            "api_key": "os.environ/ANTHROPIC_API_KEY"}},
    ]
    config = {
        "model_list": routes,
        "router_settings": {"num_retries": 0, "timeout": 60},
        "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY",
                             "background_health_checks": False, "disable_env_credential_login": True},
    }
    credentials = {key: value for key, value in bundle.credentials.items() if key != "demo_password"}
    address = bundle.public_ip
    caddy = (
        "{\n  default_sni " + address + "\n}\n\nhttps://" + address + " {\n"
        "  tls {\n    issuer acme {\n"
        "      dir https://acme-v02.api.letsencrypt.org/directory\n"
        "      profile shortlived\n    }\n  }\n"
        "  reverse_proxy gateway:4000 {\n    flush_interval -1\n  }\n}\n"
    )
    return {"gateway.json": json.dumps(config, indent=2) + "\n",
            "gateway-secrets.json": json.dumps(credentials, sort_keys=True),
            "database-password": bundle.credentials["database_password"], "Caddyfile": caddy}


def write_runtime_files(directory, bundle):
    """Only a serialized bootstrap may call this; never rotate an existing file."""
    directory = Path(directory)
    temporary = None
    try:
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise ValueError
        for name, content in runtime_files(bundle).items():
            expected = content.encode()
            path = directory / name
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                fd = None
            if fd is not None:
                with os.fdopen(fd, "rb") as stream:
                    metadata = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                            or metadata.st_mode & 0o077 or metadata.st_size != len(expected)
                            or stream.read(len(expected) + 1) != expected):
                        raise ValueError
                continue
            with tempfile.NamedTemporaryFile(mode="wb", dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(expected)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        raise GatewayError("Runtime files are inaccessible or differ from the saved deployment; preserve them for recovery") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
