"""Nonsecret runtime configuration bound to a specific attested VM and address."""

import ipaddress
import re

from .credential_identity import valid_ocid
from .gateway_config import TEXT_PATTERNS

FIELDS = {"public_ip", "public_ip_ocid", "instance_ocid",
          "presenter_email", "external_provider", "external_model_id"}


def valid_runtime_context(value):
    try:
        if not isinstance(value, dict) or set(value) != FIELDS:
            return False
        address = ipaddress.IPv4Address(value["public_ip"])
        return (
            str(address) == value["public_ip"] and address.is_global
            and not address.is_multicast
            and valid_ocid(value["public_ip_ocid"], "publicip")
            and valid_ocid(value["instance_ocid"], "instance")
            and all(isinstance(value[field], str)
                    and len(value[field]) <= 255
                    and re.fullmatch(TEXT_PATTERNS[field], value[field]) is not None
                    for field in ("presenter_email", "external_provider", "external_model_id"))
        )
    except (ValueError, TypeError, KeyError):
        return False
