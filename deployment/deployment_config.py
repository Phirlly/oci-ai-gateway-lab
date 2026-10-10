"""Strict nonsecret inputs for the implemented Terraform foundation."""

import json
import re
from dataclasses import dataclass
from types import MappingProxyType

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid

PATTERNS = {
    "tenancy_ocid": r"ocid1\.tenancy\.oc1\.\.[a-zA-Z0-9]+",
    "compartment_ocid": r"ocid1\.compartment\.oc1\.\.[a-zA-Z0-9]+",
    "region": r"[a-z]{2,}-[a-z0-9-]+-[0-9]+",
    "deployment_id": r"[a-z][a-z0-9-]{2,39}",
    "oci_model_id": r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,254}",
}
BINDING = "oci_model_key_ocid"


def _fits(name, value):
    return isinstance(value, str) and len((name + value).encode("utf-8")) <= 8192


@dataclass(frozen=True, repr=False)
class FoundationConfig:
    values: dict

    def __post_init__(self):
        try:
            if not isinstance(self.values, dict) or set(self.values) != set(PATTERNS):
                raise ValueError
            for name, pattern in PATTERNS.items():
                value = self.values[name]
                if not _fits(name, value) or re.fullmatch(pattern, value) is None:
                    raise ValueError
        except (ValueError, UnicodeError):
            raise DeliveryError("Invalid foundation settings; use the five nonsecret example fields.") from None
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def orm_variables(self, *, model_key_ocid):
        variables = dict(self.values)
        if model_key_ocid is not None:
            if not valid_ocid(model_key_ocid, "generativeaiapikey") or not _fits(BINDING, model_key_ocid):
                raise DeliveryError("Invalid recovered model-key binding.")
            variables[BINDING] = model_key_ocid
        return variables

    def read_binding(self, variables):
        if not isinstance(variables, dict) or set(variables) - set(self.values) - {BINDING}:
            raise DeliveryError("Resource Manager variables do not match the foundation settings.")
        binding = variables.get(BINDING)
        if BINDING in variables and binding is None:
            raise DeliveryError("A stored model-key binding cannot be null.")
        if variables != self.orm_variables(model_key_ocid=binding):
            raise DeliveryError("Resource Manager variables do not match the foundation settings.")
        return binding


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def load_config(content):
    """Accept the same JSON text from a protected file or GitHub variable."""
    try:
        if not isinstance(content, (bytes, str)):
            raise ValueError
        encoded = content.encode("utf-8") if isinstance(content, str) else content
        if len(encoded) > 48 * 1024:
            raise ValueError
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise DeliveryError("Invalid foundation JSON; supply one bounded, duplicate-free object.") from None
    if isinstance(value, dict) and "schema_version" in value:
        from .gateway_config import GatewayConfig
        return GatewayConfig(value)
    return FoundationConfig(value)
