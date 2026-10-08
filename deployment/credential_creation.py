"""Prepare bounded runtime credentials before requesting a one-time OCI key."""

import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .credential_errors import DeliveryError
from .credential_identity import valid_identity
from .credential_records import MAX_RECORD_BYTES, CredentialRecord, intent_request, parse_record, valid_secret

# Component-supported budgets, not OCI service limits.
MODEL_KEY_BYTES = 8192
MODEL_KEY_OCID_CHARS = 512


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True, repr=False)
class CredentialDraft:
    intent: CredentialRecord
    credentials: Mapping[str, str]


def _runtime_value(draft, key_id, key):
    value = json.loads(draft.intent.content)
    del value["retry_policy"]
    del value["request"]
    value.update(kind="runtime-bundle", model_key_ocid=key_id,
                 credentials={**draft.credentials, "oci_api_key": key})
    return value


def prepare_credentials(identity, external_api_key, demo_password, expires_at, *, now):
    if not valid_identity(identity):
        raise DeliveryError("Invalid deployment identity.")
    if not valid_secret(external_api_key) or not valid_secret(demo_password):
        raise DeliveryError("External key and demo password must be valid nonempty credentials.")
    operation = secrets.token_hex(16)
    value = {
        "schema_version": 1, "kind": "creation-intent", "identity": dict(identity),
        "operation_id": operation, "expires_at": expires_at,
        "retry_policy": "no-automatic-retry",
        "request": intent_request(identity, operation, expires_at),
    }
    try:
        intent = parse_record(_encoded(value), dict(identity))
        intent.require_unexpired(now)
        draft = CredentialDraft(intent, MappingProxyType({
            "external_api_key": external_api_key,
            "demo_password": demo_password,
            "database_password": secrets.token_hex(24),
            "gateway_master_key": "sk-" + secrets.token_hex(24),
            "gateway_salt_key": secrets.token_hex(32),
        }))
        reserved_size = len(_encoded(_runtime_value(draft, "", ""))) + MODEL_KEY_BYTES + MODEL_KEY_OCID_CHARS
        if reserved_size > MAX_RECORD_BYTES:
            raise DeliveryError("Supplied credentials exceed supported runtime bundle capacity.")
        return draft
    except (TypeError, ValueError, UnicodeError):
        raise DeliveryError("Credential inputs cannot be encoded safely.") from None


def runtime_record(draft, key_id, key):
    try:
        if not valid_secret(key) or len(_encoded(key)) - 2 > MODEL_KEY_BYTES:
            raise DeliveryError("Model key exceeds supported credential capacity.")
        if not isinstance(key_id, str) or len(key_id) > MODEL_KEY_OCID_CHARS:
            raise DeliveryError("Model key identifier exceeds supported capacity.")
        value = _runtime_value(draft, key_id, key)
        return parse_record(_encoded(value), value["identity"])
    except (TypeError, ValueError, UnicodeError):
        raise DeliveryError("Model credentials cannot be encoded safely.") from None
