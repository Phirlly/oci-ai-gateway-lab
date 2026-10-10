"""Serialized resumable VM initialization; presenter completion ends polling."""

import fcntl
import json
import os
import stat
import sys
from pathlib import Path

from .cloud_credentials import current_content, instance_id
from .gateway_http import GatewayError, GatewayHTTP
from .host_commands import ensure_dependencies, start_services, stop_bootstrap_timer
from .host_firewall import protect_metadata
from .presenter import Presenter, initialize_presenter
from .presenter_api import PresenterAPI
from .presenter_state import PresenterState
from .runtime_bundle import BundlePending, MODEL_ALIASES, load_bundle, validate_settings
from .runtime_files import write_runtime_files

STATE = Path("/var/lib/oci-ai-gateway")


def initialize(settings, directory, *, now=None):
    settings = validate_settings(settings)
    presenter = Presenter(settings["deployment_id"], settings["presenter_email"], MODEL_ALIASES)
    state = PresenterState(directory, presenter)
    saved = state.load()
    if saved is not None and saved["phase"] == "complete":
        return
    ensure_dependencies()
    protect_metadata()
    identifier = instance_id(settings)
    bundle = load_bundle(current_content(settings), settings, identifier, now=now)
    write_runtime_files(directory, bundle)
    start_services()
    public = GatewayHTTP("http://127.0.0.1:4000", allow_loopback=True)
    admin = GatewayHTTP(public.base_url, bundle.credentials["gateway_master_key"], allow_loopback=True)
    initialize_presenter(PresenterAPI(admin, public), state, presenter, bundle.credentials["demo_password"])


def main():
    try:
        if os.geteuid() != 0:
            raise GatewayError("VM bootstrap requires the dedicated root service")
        metadata = STATE.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o077:
            raise GatewayError("Bootstrap state directory must be private and root-owned")
        fd = os.open(STATE / "bootstrap.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(fd, "r+") as lock:
            metadata = os.fstat(lock.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o077:
                raise GatewayError("Invalid bootstrap lock")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            content = Path("/etc/oci-ai-gateway.json").read_bytes()
            if len(content) > 8192:
                raise GatewayError("Runtime settings exceeded their size limit")
            initialize(json.loads(content), STATE)
            stop_bootstrap_timer()
        print("Gateway initialized; public TLS and model verification are performed by the deployment workflow")
        return 0
    except BundlePending:
        print("Waiting for CURRENT credentials; bootstrap timer will retry")
        return 75
    except GatewayError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, RecursionError):
        print("Bootstrap input, lock or local state could not be verified", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
