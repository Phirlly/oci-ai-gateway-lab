"""Private durable phases for the single deployment-owned presenter."""

import json
import os
import re
import stat
import tempfile
from pathlib import Path

from .gateway_http import GatewayError

PHASES = {"user-started", "invitation-started", "invitation-created", "claim-started", "complete"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class PresenterState:
    def __init__(self, directory, presenter):
        self.directory = Path(directory)
        self.path = self.directory / "presenter.json"
        self.fingerprint = presenter.fingerprint

    def _directory(self):
        metadata = self.directory.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077):
            raise ValueError

    def _validate(self, value):
        if (not isinstance(value, dict)
                or set(value) != {"schema_version", "presenter", "phase", "invitation"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["presenter"] != self.fingerprint or value["phase"] not in PHASES):
            raise ValueError
        invitation = value["invitation"]
        if value["phase"] in ("user-started", "invitation-started"):
            if invitation is not None:
                raise ValueError
        elif not isinstance(invitation, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", invitation) is None:
            raise ValueError
        return value

    def load(self):
        try:
            self._directory()
            try:
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                return None
            with os.fdopen(fd, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                        or metadata.st_mode & 0o077 or metadata.st_size > 8192):
                    raise ValueError
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise ValueError
            return self._validate(json.loads(raw, object_pairs_hook=_object))
        except (OSError, ValueError, TypeError, RecursionError):
            raise GatewayError("Presenter state is invalid or inaccessible; preserve it for recovery") from None

    def save(self, phase, invitation=None):
        temporary = None
        try:
            self._directory()
            self.load()  # Do not overwrite corrupt, foreign or unsafe evidence.
            value = self._validate({"schema_version": 1, "presenter": self.fingerprint,
                                    "phase": phase, "invitation": invitation})
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(value, separators=(",", ":")).encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except (OSError, ValueError, TypeError):
            raise GatewayError("Presenter state could not be persisted; stop initialization") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
