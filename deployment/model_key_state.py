"""Validate GenAI resource ownership and the exact usable credential slot."""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .credential_records import intent_request, valid_secret

RESOURCE_STATES = {"CREATING", "ACTIVE", "INACTIVE", "UPDATING", "DELETING", "DELETED", "FAILED"}
SLOT_STATES = {"ACTIVE", "INACTIVE", "REVOKED", "EXPIRED", "DELETED"}


@dataclass(frozen=True, repr=False)
class ModelKey:
    key_id: str
    secret: str | None


def parse_model_key(response, record, *, now, expected_key_id=None,
                    require_secret=False, require_active=False):
    record.require_unexpired(now)
    try:
        value = json.loads(record.content)
        expected = intent_request(value["identity"], record.operation_id, value["expires_at"])
        data = response["data"]
        key_id, tags = data["id"], data["freeform-tags"]
        binding = expected_key_id or record.model_key_ocid
        if (
            not valid_ocid(key_id, "generativeaiapikey")
            or (binding is not None and key_id != binding)
            or data["compartment-id"] != expected["compartmentId"]
            or data["display-name"] != expected["displayName"]
            or not isinstance(tags, dict)
            or any(tags.get(name) != item for name, item in expected["freeformTags"].items())
            or data["lifecycle-state"] not in RESOURCE_STATES
        ):
            raise ValueError("Ownership")
        slots = data["keys"]
        if not isinstance(slots, list):
            raise ValueError("Slots")
        matches = [slot for slot in slots if slot["key-name"] == "gateway"]
        if len(matches) != 1:
            raise ValueError("Gateway slot")
        slot = matches[0]
        expiry = datetime.fromisoformat(slot["time-expiry"])
        if expiry.tzinfo is None or expiry != record.expires_at or slot["state"] not in SLOT_STATES:
            raise ValueError("Expiry or state")
        secret = None
        if require_secret:
            if data["lifecycle-state"] not in {"CREATING", "ACTIVE"} or not valid_secret(slot.get("key")):
                raise ValueError("One-time value")
            secret = slot["key"]
        if require_active and (data["lifecycle-state"] != "ACTIVE" or slot["state"] != "ACTIVE"):
            raise ValueError("Not active")
        return ModelKey(key_id, secret)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError("Model key ownership, expiry, state or credential could not be verified.") from None


def owned_candidates(response, identity):
    """Empty discovery never authorizes retry of an existing creation intent."""
    try:
        rows = response["data"]["items"]
        if not isinstance(rows, list):
            raise ValueError("Collection")
        candidates, seen = [], set()
        for row in rows:
            key_id, tags = row["id"], row.get("freeform-tags")
            if tags is None:
                tags = {}
            if not valid_ocid(key_id, "generativeaiapikey") or key_id in seen or not isinstance(tags, dict):
                raise ValueError("Collection entry")
            seen.add(key_id)
            belongs = tags.get("solution") == "oci-ai-gateway-lab" and tags.get("deployment_id") == identity["deployment_id"]
            if not belongs and row["display-name"] != identity["deployment_id"] + "-model":
                continue
            if (
                not belongs or row["compartment-id"] != identity["compartment_ocid"]
                or tags.get("stack_ocid") != identity["stack_ocid"]
                or not isinstance(tags.get("operation_id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", tags["operation_id"])
            ):
                raise ValueError("Conflicting ownership")
            candidates.append(key_id)
        return tuple(candidates)
    except (KeyError, TypeError, ValueError):
        raise DeliveryError("Model key discovery has conflicting or unverified ownership.") from None
