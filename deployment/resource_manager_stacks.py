"""Read-only stack ownership and foundation-variable observations."""

import re
from dataclasses import dataclass

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .deployment_config import FoundationConfig

STACK_STATES = {"CREATING", "ACTIVE", "DELETING", "DELETED", "FAILED"}


@dataclass(frozen=True, repr=False)
class StackTarget:
    config: FoundationConfig
    controller_id: str

    def __post_init__(self):
        if (not isinstance(self.config, FoundationConfig)
                or not isinstance(self.controller_id, str)
                or re.fullmatch(r"[a-f0-9]{64}", self.controller_id) is None):
            raise DeliveryError("Invalid Resource Manager controller identity.")

    @property
    def tags(self):
        return {"solution": "oci-ai-gateway-lab",
                "deployment_id": self.config.values["deployment_id"],
                "controller_id": self.controller_id}

    @property
    def compartment_id(self):
        return self.config.values["compartment_ocid"]

    def owns(self, data):
        tags = data.get("freeform-tags")
        return (isinstance(tags, dict) and all(tags.get(k) == v for k, v in self.tags.items())
                and data.get("compartment-id") == self.compartment_id)


@dataclass(frozen=True, repr=False)
class StackSnapshot:
    stack_id: str
    state: str
    etag: str
    model_key_ocid: str | None


def find_stack(response, target):
    """Absence is an observation, never permission to create or resubmit."""
    try:
        rows = response["data"]
        if not isinstance(rows, list):
            raise ValueError
        seen, matches = set(), []
        for row in rows:
            stack_id = row["id"]
            if not valid_ocid(stack_id, "ormstack") or stack_id in seen:
                raise ValueError
            seen.add(stack_id)
            tags = row.get("freeform-tags")
            tags = {} if tags is None else tags
            if not isinstance(tags, dict):
                raise ValueError
            candidate = (
                tags.get("solution") == target.tags["solution"]
                and tags.get("deployment_id") == target.tags["deployment_id"]
            )
            if candidate:
                if not target.owns(row):
                    raise ValueError
                matches.append(stack_id)
            elif row.get("display-name") == target.config.values["deployment_id"]:
                raise ValueError
        if len(matches) > 1:
            raise ValueError
        return matches[0] if matches else None
    except (KeyError, TypeError, ValueError):
        raise DeliveryError("Stack discovery has malformed or conflicting ownership; reconcile before proceeding.") from None


def parse_stack(response, target, expected_id):
    try:
        data, etag = response["data"], response["etag"]
        if (not valid_ocid(expected_id, "ormstack") or data["id"] != expected_id
                or not target.owns(data) or data["lifecycle-state"] not in STACK_STATES
                or not isinstance(etag, str) or not etag):
            raise ValueError
        binding = target.config.read_binding(data["variables"])
        return StackSnapshot(expected_id, data["lifecycle-state"], etag, binding)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError("Exact owned stack metadata could not be verified.") from None
