"""Strict, immutable records for intent staging and runtime publication."""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from .credential_errors import DeliveryError
from .credential_identity import valid_identity, valid_ocid

MAX_RECORD_BYTES = 16384
SECRET_FIELDS = {
    "oci_api_key", "external_api_key", "database_password",
    "gateway_master_key", "gateway_salt_key", "demo_password",
}
BASE_FIELDS = {"schema_version", "kind", "identity", "operation_id", "expires_at"}


@dataclass(frozen=True, repr=False)
class CredentialRecord:
    content: bytes
    kind: str
    operation_id: str
    expires_at: datetime
    model_key_ocid: str | None = None

    @property
    def version_name(self):
        prefix = "intent" if self.kind == "creation-intent" else "runtime"
        return prefix + "-" + self.operation_id

    def require_unexpired(self, now):
        if now.tzinfo is None or self.expires_at <= now:
            raise DeliveryError("Credential record expired; explicit recovery is required.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


def intent_request(identity, operation, expiry):
    return {
        "compartmentId": identity["compartment_ocid"],
        "displayName": identity["deployment_id"] + "-model",
        "keyDetails": [{"keyName": "gateway", "timeExpiry": expiry}],
        "freeformTags": {
            "solution": "oci-ai-gateway-lab",
            "deployment_id": identity["deployment_id"],
            "stack_ocid": identity["stack_ocid"],
            "operation_id": operation,
        },
    }


def valid_secret(value):
    return (
        isinstance(value, str) and 0 < len(value) <= 8192
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def parse_record(content, identity):
    """Reject malformed/wrong-owner records without echoing their contents."""
    try:
        if not isinstance(content, bytes) or len(content) > MAX_RECORD_BYTES:
            raise ValueError("Size or encoding")
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(value, dict) or not valid_identity(identity):
            raise ValueError("Identity")
        if value.get("identity") != identity or type(value.get("schema_version")) is not int:
            raise ValueError("Identity or schema")
        if value["schema_version"] != 1:
            raise ValueError("Schema")
        operation = value["operation_id"]
        if not isinstance(operation, str) or not re.fullmatch(r"[a-f0-9]{32}", operation):
            raise ValueError("Operation")
        expiry = value["expires_at"]
        if not isinstance(expiry, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", expiry):
            raise ValueError("Expiry")
        expiry_time = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        kind = value["kind"]
        key_id = None
        if kind == "creation-intent":
            if set(value) != BASE_FIELDS | {"retry_policy", "request"}:
                raise ValueError("Intent fields")
            if value["retry_policy"] != "no-automatic-retry":
                raise ValueError("Retry policy")
            if value["request"] != intent_request(identity, operation, expiry):
                raise ValueError("Intent request")
        elif kind == "runtime-bundle":
            if set(value) != BASE_FIELDS | {"model_key_ocid", "credentials"}:
                raise ValueError("Runtime fields")
            key_id = value["model_key_ocid"]
            credentials = value["credentials"]
            if not valid_ocid(key_id, "generativeaiapikey"):
                raise ValueError("Key identity")
            if not isinstance(credentials, dict) or set(credentials) != SECRET_FIELDS:
                raise ValueError("Credentials")
            if not all(valid_secret(secret) for secret in credentials.values()):
                raise ValueError("Credentials")
        else:
            raise ValueError("Record type")
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return CredentialRecord(canonical, kind, operation, expiry_time, key_id)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise DeliveryError("Invalid credential record: check schema, identity, expiry and required fields.") from None
