"""Validate the VM's CURRENT v2 bundle independently of deployment orchestration."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import IPv4Address
from types import MappingProxyType

from .gateway_http import GatewayError
from .password_policy import valid_presenter_password
from .presenter import Presenter

REGION = r"[a-z]{2,}-[a-z0-9-]+-[0-9]+"
SETTINGS_PATTERNS = {
    "deployment_id": r"[a-z][a-z0-9-]{2,39}",
    "tenancy_ocid": r"ocid1\.tenancy\.oc1\.\.[a-zA-Z0-9._-]+",
    "compartment_ocid": r"ocid1\.compartment\.oc1\.\.[a-zA-Z0-9._-]+",
    "secret_ocid": r"ocid1\.vaultsecret\.oc1\.[a-z0-9-]+\.[a-zA-Z0-9._-]+",
    "region": REGION, "inference_region": REGION,
    "model_id": r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,254}",
    "presenter_email": r"[a-zA-Z0-9._+%-]{1,64}@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+",
    "external_provider": r"anthropic", "external_model_id": r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}",
}
IDENTITY_FIELDS = {"deployment_id", "tenancy_ocid", "compartment_ocid", "secret_ocid", "inference_region", "model_id"}
RUNTIME_FIELDS = {"public_ip", "public_ip_ocid", "instance_ocid", "presenter_email", "external_provider", "external_model_id"}
CREDENTIAL_FIELDS = {"oci_api_key", "external_api_key", "database_password", "gateway_master_key", "gateway_salt_key", "demo_password"}
MODEL_ALIASES = ("oci-managed", "external-anthropic")


class BundlePending(GatewayError):
    """Foundation exists but its runtime credentials have not been published."""


@dataclass(frozen=True, repr=False)
class RuntimeBundle:
    settings: object
    public_ip: str
    credentials: object
    presenter: Presenter


def _matches(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _ocid(value, kind):
    return _matches(value, rf"ocid1\.{kind}\.oc1\.[a-z0-9-]+\.[a-zA-Z0-9._-]+")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def validate_settings(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", *SETTINGS_PATTERNS}
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or any(not isinstance(value[key], str) or len(value[key]) > 512
                   or not _matches(value[key], pattern) for key, pattern in SETTINGS_PATTERNS.items())):
        raise GatewayError("Invalid runtime deployment settings")
    return dict(value)


def _validate_owner(value, settings, instance_id):
    identity, runtime = value["identity"], value["runtime"]
    if (not isinstance(identity, dict) or set(identity) != IDENTITY_FIELDS | {"stack_ocid"}
            or any(identity[key] != settings[key] for key in IDENTITY_FIELDS)
            or not _ocid(identity["stack_ocid"], "ormstack")
            or not isinstance(runtime, dict) or set(runtime) != RUNTIME_FIELDS
            or not _ocid(instance_id, "instance") or runtime["instance_ocid"] != instance_id
            or not _ocid(runtime["public_ip_ocid"], "publicip")
            or any(runtime[key] != settings[key] for key in ("presenter_email", "external_provider", "external_model_id"))):
        raise ValueError
    address = IPv4Address(runtime["public_ip"])
    if str(address) != runtime["public_ip"] or not address.is_global or address.is_multicast:
        raise ValueError
    return str(address)


def load_bundle(content, settings, instance_id, *, now=None):
    settings = validate_settings(settings)
    if content == b"UNCONFIGURED":
        raise BundlePending("Waiting for CURRENT runtime credentials")
    try:
        if not isinstance(content, bytes) or len(content) > 16384:
            raise ValueError
        value = json.loads(content, object_pairs_hook=_unique)
        if (not isinstance(value, dict) or set(value) != {
                "schema_version", "kind", "identity", "operation_id", "expires_at",
                "model_key_ocid", "runtime", "credentials"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 2
                or value["kind"] != "runtime-bundle" or not _matches(value["operation_id"], r"[a-f0-9]{32}")
                or not _ocid(value["model_key_ocid"], "generativeaiapikey")
                or not _matches(value["expires_at"], r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")):
            raise ValueError
        expiry = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
        current = now if now is not None else datetime.now(timezone.utc)
        if current.tzinfo is None or expiry <= current:
            raise ValueError
        public_ip = _validate_owner(value, settings, instance_id)
        credentials = value["credentials"]
        if (not isinstance(credentials, dict) or set(credentials) != CREDENTIAL_FIELDS
                or any(not isinstance(item, str) or not 0 < len(item) <= 8192
                       or any(ord(c) < 32 or ord(c) == 127 for c in item)
                       for item in credentials.values())
                or not valid_presenter_password(credentials["demo_password"])):
            raise ValueError
        presenter = Presenter(settings["deployment_id"], settings["presenter_email"], MODEL_ALIASES)
        return RuntimeBundle(MappingProxyType(settings), public_ip,
                             MappingProxyType(dict(credentials)), presenter)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, AttributeError):
        raise GatewayError("CURRENT runtime bundle is invalid, expired or belongs to another deployment") from None
