"""Synthetic credential documents shared only by deployment unit tests."""

import json
from datetime import datetime, timezone

IDENTITY = {
    "deployment_id": "gateway-test",
    "tenancy_ocid": "ocid1.tenancy.oc1..example",
    "compartment_ocid": "ocid1.compartment.oc1..example",
    "stack_ocid": "ocid1.ormstack.oc1.iad.example",
    "secret_ocid": "ocid1.vaultsecret.oc1.iad.example",
    "inference_region": "us-chicago-1",
    "model_id": "example.chat-model",
}
OPERATION = "a" * 32
KEY_ID = "ocid1.generativeaiapikey.oc1.ord.example"
EXPIRES = "2030-01-02T00:00:00Z"
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def document(kind="runtime-bundle", operation=OPERATION):
    value = {
        "schema_version": 1,
        "kind": kind,
        "identity": dict(IDENTITY),
        "operation_id": operation,
        "expires_at": EXPIRES,
    }
    if kind == "creation-intent":
        value["retry_policy"] = "no-automatic-retry"
        value["request"] = {
            "compartmentId": IDENTITY["compartment_ocid"],
            "displayName": "gateway-test-model",
            "keyDetails": [{"keyName": "gateway", "timeExpiry": EXPIRES}],
            "freeformTags": {
                "solution": "oci-ai-gateway-lab",
                "deployment_id": IDENTITY["deployment_id"],
                "stack_ocid": IDENTITY["stack_ocid"],
                "operation_id": operation,
            },
        }
    else:
        value["model_key_ocid"] = KEY_ID
        value["credentials"] = {
            name: "synthetic-" + name for name in (
                "oci_api_key", "external_api_key", "database_password",
                "gateway_master_key", "gateway_salt_key", "demo_password",
            )
        }
    return value


def encoded(value):
    return json.dumps(value).encode("utf-8")
