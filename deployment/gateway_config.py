"""Versioned complete settings for the supported two-provider CPU deployment."""

import json
import re
from types import MappingProxyType

from .credential_errors import DeliveryError
from .deployment_config import FoundationConfig, PATTERNS

TEXT_PATTERNS = {
    "inference_region": PATTERNS["region"],
    "external_provider": r"anthropic",
    "external_model_id": r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}",
    "presenter_email": r"[a-zA-Z0-9._+%-]{1,64}@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+",
    "instance_shape": r"VM\.Standard\.E[45]\.Flex",
    "image_name": r"Canonical-Ubuntu-24\.04-\d{4}\.\d{2}\.\d{2}-\d+",
}
# Deliberate demo bounds, narrower than OCI's service limits.
INTEGER_LIMITS = {
    "schema_version": (2, 2),
    "instance_ocpus": (1, 16),
    "instance_memory_gbs": (8, 256),
    "boot_volume_size_gbs": (50, 500),
    "availability_domain_number": (1, 3),
    "model_key_ttl_days": (1, 30),
}


class GatewayConfig(FoundationConfig):
    def __post_init__(self):
        try:
            value = self.values
            if not isinstance(value, dict) or set(value) != set(PATTERNS) | set(TEXT_PATTERNS) | set(INTEGER_LIMITS):
                raise ValueError
            FoundationConfig({name: value[name] for name in PATTERNS})
            for name, pattern in TEXT_PATTERNS.items():
                item = value[name]
                if not isinstance(item, str) or len(item) > 255 or re.fullmatch(pattern, item) is None:
                    raise ValueError
            for name, (low, high) in INTEGER_LIMITS.items():
                item = value[name]
                if type(item) is not int or not low <= item <= high:
                    raise ValueError
            if not value["instance_ocpus"] <= value["instance_memory_gbs"] <= 64 * value["instance_ocpus"]:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise DeliveryError("Invalid gateway settings; check the complete version2 example and supported bounds.") from None
        object.__setattr__(self, "values", MappingProxyType(dict(value)))

    def orm_variables(self, *, model_key_ocid):
        values = super().orm_variables(model_key_ocid=model_key_ocid)
        return {key: json.dumps(value) if type(value) is int else value
                for key, value in values.items()}
