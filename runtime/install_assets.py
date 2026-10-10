"""Extract the attested cloud-init JSON map before enabling any network work."""

import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

SPECIAL = {
    "runtime/systemd/oci-ai-gateway-bootstrap.service": "etc/systemd/system/oci-ai-gateway-bootstrap.service",
    "runtime/systemd/oci-ai-gateway-bootstrap.timer": "etc/systemd/system/oci-ai-gateway-bootstrap.timer",
    "runtime/systemd/docker-guard.conf": "etc/systemd/system/docker.service.d/10-gateway-guard.conf",
    "runtime/docker-daemon.json": "etc/docker/daemon.json",
}


def install_assets(content, root=Path("/")):
    if not isinstance(content, bytes) or len(content) > 256 * 1024:
        raise ValueError("Invalid asset payload")
    values = json.loads(content)
    if not isinstance(values, dict) or not 1 <= len(values) <= 32:
        raise ValueError("Invalid asset manifest")
    destinations = {}
    for name, body in values.items():
        if not isinstance(body, str) or len(body.encode()) > 65536:
            raise ValueError("Invalid asset content")
        if name in SPECIAL:
            destination = SPECIAL[name]
        elif re.fullmatch(r"runtime/[a-z_]+\.py", name) or name == "runtime/compose.cloud.yaml":
            destination = "opt/oci-ai-gateway/" + name
        else:
            raise ValueError("Unrecognized asset path")
        destinations[destination] = body.encode()
    for relative, data in destinations.items():
        path = root / relative
        parent = root
        for component in Path(relative).parts[:-1]:
            parent = parent / component
            parent.mkdir(mode=0o755, exist_ok=True)
            metadata = parent.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
                raise ValueError("Unsafe asset directory")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".gateway-asset-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o644)
                    os.fsync(stream.fileno())
                # Atomic publication without overwriting a concurrent/conflicting file.
                os.link(temporary, path, follow_symlinks=False)
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        else:
            with os.fdopen(fd, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                        or metadata.st_mode & 0o022 or stream.read(65537) != data):
                    raise ValueError("Existing asset differs from the deployment")


if __name__ == "__main__":
    try:
        install_assets(Path("/opt/oci-ai-gateway/assets.json").read_bytes())
    except (OSError, ValueError, TypeError, RecursionError):
        print("Embedded runtime assets could not be installed safely", file=sys.stderr)
        sys.exit(1)
