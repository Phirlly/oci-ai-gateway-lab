"""Protected OCI signing inputs; profile names never enter deployment settings."""

import configparser
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid


@dataclass(frozen=True, repr=False)
class Connection:
    config_file: str
    profile: str


def _signing_fields(environment, tenancy):
    try:
        user = environment["OCI_USER_OCID"]
        fingerprint = environment["OCI_FINGERPRINT"]
        key = environment["OCI_PRIVATE_KEY"]
        password = environment.get("OCI_PRIVATE_KEY_PASSPHRASE", "")
        if (not valid_ocid(tenancy, "tenancy") or not valid_ocid(user, "user")
                or not isinstance(fingerprint, str)
                or re.fullmatch(r"(?:[a-fA-F0-9]{2}:){15}[a-fA-F0-9]{2}", fingerprint) is None
                or not isinstance(key, str) or len(key) > 16384
                or re.fullmatch(r"-----BEGIN ((?:RSA |ENCRYPTED )?PRIVATE KEY)-----\r?\n"
                                r"[a-zA-Z0-9+/=\r\n]+"
                                r"-----END \1-----(?:\r?\nOCI_API_KEY)?\s*", key) is None
                or not isinstance(password, str) or len(password) > 1024
                or any(ord(c) < 32 or ord(c) == 127 for c in password)):
            raise ValueError
        return user, fingerprint, key, password
    except (KeyError, TypeError, ValueError):
        raise DeliveryError("OCI signing secrets are missing or malformed; check environment secret names.") from None


@contextmanager
def runner_connection(environment, tenancy):
    user, fingerprint, key, password = _signing_fields(environment, tenancy)
    with tempfile.TemporaryDirectory(prefix="gateway-signing-") as directory:
        root = Path(directory)
        key_path, config_path = root / "key.pem", root / "config"
        config = configparser.ConfigParser(interpolation=None)
        config["DEFAULT"] = {
            "user": user, "tenancy": tenancy, "fingerprint": fingerprint,
            "key_file": str(key_path),
        }
        if password:
            config["DEFAULT"]["pass_phrase"] = password
        try:
            for path in (key_path, config_path):
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    if path == key_path:
                        output.write(key)
                    else:
                        config.write(output)
            yield Connection(str(config_path), "DEFAULT")
        except OSError:
            raise DeliveryError("Protected deployment signing files could not be used.") from None


def local_connection(config_file, profile, tenancy):
    """Inspect the selected profile; actual signing remains the pinned CLI's job."""
    try:
        if (not isinstance(profile, str) or not profile or len(profile) > 128
                or any(ord(c) < 32 for c in profile) or not valid_ocid(tenancy, "tenancy")):
            raise ValueError
        path = Path(config_file).expanduser().resolve(strict=True)
        config = configparser.ConfigParser(interpolation=None)
        with path.open(encoding="utf-8") as source:
            config.read_file(source)
        if profile not in config or config[profile].get("tenancy") != tenancy:
            raise ValueError
        return Connection(str(path), profile)
    except (OSError, UnicodeError, ValueError, configparser.Error):
        raise DeliveryError("Selected OCI profile is missing or does not match the configured tenancy.") from None
