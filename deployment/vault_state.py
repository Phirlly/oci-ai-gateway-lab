"""Validate owned Vault metadata and exact secret versions before decisions."""

import base64
import binascii
import time
from dataclasses import dataclass
from types import MappingProxyType

from .credential_errors import DeliveryError, VaultReadError
from .credential_identity import valid_identity, valid_ocid
from .credential_records import MAX_RECORD_BYTES, CredentialRecord, parse_record


@dataclass(frozen=True)
class VaultTarget:
    identity: dict
    vault_ocid: str
    key_ocid: str

    def __post_init__(self):
        if not valid_identity(self.identity):
            raise DeliveryError("Invalid deployment identity.")
        if not valid_ocid(self.vault_ocid, "vault") or not valid_ocid(self.key_ocid, "key"):
            raise DeliveryError("Invalid Vault resource identifiers.")
        object.__setattr__(self, "identity", MappingProxyType(dict(self.identity)))

    @property
    def secret_id(self):
        return self.identity["secret_ocid"]


@dataclass(frozen=True, repr=False)
class SecretVersion:
    number: int
    name: str
    stages: tuple
    record: CredentialRecord | None


@dataclass(frozen=True)
class CurrentSnapshot:
    etag: str
    version: SecretVersion


def _version_number(value):
    return type(value) is int and value > 0


def _stages(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) for item in value)


def read_version_content(client, target, *, number=None, name=None):
    """Validate the envelope only; callers own record purpose and expiry rules."""
    response = client.bundle(target.secret_id, version_number=number, version_name=name)
    try:
        data = response["data"]
        version_number = data["version-number"]
        version_name = data["version-name"]
        stages = data["stages"]
        encoded = data["secret-bundle-content"]
        if (
            data["secret-id"] != target.secret_id or not _version_number(version_number)
            or not isinstance(version_name, str) or not _stages(stages)
            or (number is not None and version_number != number)
            or (name is not None and version_name != name)
            or encoded["content-type"] != "BASE64"
        ):
            raise ValueError("Version metadata")
        content = base64.b64decode(encoded["content"], validate=True)
        if len(content) > MAX_RECORD_BYTES:
            raise ValueError('Content exceeds supported record size')
        return version_number, version_name, tuple(stages), content
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise DeliveryError("Secret version identity or content could not be verified.") from None


def read_version(client, target, now, *, number=None, name=None):
    version_number, version_name, stages, content = read_version_content(client, target, number=number, name=name)
    try:
        if content == b"UNCONFIGURED":
            if version_name != "unconfigured" or version_number != 1:
                raise ValueError("Placeholder")
            record = None
        else:
            record = parse_record(content, dict(target.identity))
            record.require_unexpired(now)
            if record.version_name != version_name:
                raise ValueError("Version name")
        return SecretVersion(version_number, version_name, tuple(stages), record)
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise DeliveryError("Secret version identity or content could not be verified.") from None


def _owned_metadata(response, target):
    try:
        data = response["data"]
        etag = response["etag"]
        tags = data["freeform-tags"]
        if (
            data["id"] != target.secret_id
            or data["compartment-id"] != target.identity["compartment_ocid"]
            or data["vault-id"] != target.vault_ocid or data["key-id"] != target.key_ocid
            or data["lifecycle-state"] not in ("ACTIVE", "UPDATING")
            or tags["solution"] != "oci-ai-gateway-lab"
            or tags["deployment_id"] != target.identity["deployment_id"]
            or not isinstance(etag, str) or not etag
            or not _version_number(data["current-version-number"])
        ):
            raise ValueError("Ownership")
        number = data["current-version-number"]
    except (KeyError, TypeError, ValueError):
        raise DeliveryError("Owned secret metadata could not be verified.") from None
    return data["lifecycle-state"], etag, number


def read_secret_metadata(client, target):
    """Wait for owned updates using one budget for transport and readiness."""
    for delay in (2, 4, 8, 16, 30, None):
        try:
            response = client.metadata(target.secret_id)
        except VaultReadError:
            pass
        else:
            state, etag, number = _owned_metadata(response, target)
            if state == "ACTIVE":
                return etag, number
        if delay is not None:
            time.sleep(delay)
    raise VaultReadError("Owned secret readiness could not be verified after bounded reads.") from None


def read_current(client, target, now):
    etag, number = read_secret_metadata(client, target)
    # The version is selected by this metadata snapshot, not a second CURRENT read.
    version = read_version(client, target, now, number=number)
    if "CURRENT" not in version.stages:
        raise DeliveryError("CURRENT changed during reconciliation; retry the read.")
    if version.record is not None and version.record.kind != "runtime-bundle":
        raise DeliveryError("CURRENT must be a runtime bundle or the initial placeholder.")
    return CurrentSnapshot(etag, version)


def read_staged(client, target, now):
    """Read durable history while CURRENT is the verified initial placeholder."""
    try:
        rows = client.versions(target.secret_id)["data"]
        if not isinstance(rows, list) or len(rows) > 128:
            raise ValueError("Version list")
        selected, names, numbers = [], set(), set()
        for row in rows:
            name, number, stages = row["name"], row["version-number"], row["stages"]
            if (
                row["secret-id"] != target.secret_id or not isinstance(name, str)
                or not _version_number(number) or not _stages(stages)
                or name in names or number in numbers
            ):
                raise ValueError("Version list entry")
            names.add(name)
            numbers.add(number)
            if name == "unconfigured" and number == 1 and "CURRENT" in stages:
                continue
            selected.append((name, number))
    except (KeyError, TypeError, ValueError):
        raise DeliveryError("Vault version discovery could not be verified.") from None
    versions = []
    for name, number in selected:
        version = read_version(client, target, now, name=name)
        if version.number != number or "CURRENT" in version.stages:
            raise DeliveryError("Staged version changed during reconciliation.")
        if version.record is None:
            raise DeliveryError("A staged placeholder cannot be delivered.")
        # An earlier intent may lose PENDING when runtime content is uploaded.
        # Its exact named record still prevents an unsafe new creation attempt.
        if version.record.kind == "runtime-bundle" and "PENDING" not in version.stages:
            raise DeliveryError("Staged runtime credentials must remain PENDING.")
        versions.append(version)
    operations = {version.record.operation_id for version in versions}
    kinds = [version.record.kind for version in versions]
    if len(operations) > 1 or len(kinds) != len(set(kinds)):
        raise DeliveryError("Conflicting pending credential records require explicit recovery.")
    runtime = [version for version in versions if version.record.kind == "runtime-bundle"]
    intent = [version for version in versions if version.record.kind == "creation-intent"]
    if runtime and (not intent or runtime[0].record.expires_at != intent[0].record.expires_at
                    or runtime[0].record.runtime_context != intent[0].record.runtime_context):
        raise DeliveryError("Pending runtime credentials require a matching durable intent.")
    return versions
