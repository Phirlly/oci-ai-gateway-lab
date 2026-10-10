"""Synthetic wire-format bundle matching the deployed v2 credential contract."""

from datetime import datetime, timezone

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
INSTANCE = "ocid1.instance.oc1.iad.synthetic"
SETTINGS = {
    "schema_version": 1, "deployment_id": "synthetic-demo",
    "tenancy_ocid": "ocid1.tenancy.oc1..synthetic",
    "compartment_ocid": "ocid1.compartment.oc1..synthetic",
    "secret_ocid": "ocid1.vaultsecret.oc1.iad.synthetic", "region": "us-ashburn-1",
    "inference_region": "us-ashburn-1", "model_id": "synthetic-model",
    "presenter_email": "presenter@example.invalid", "external_provider": "anthropic",
    "external_model_id": "synthetic-external",
}


def bundle():
    return {
        "schema_version": 2, "kind": "runtime-bundle", "operation_id": "a" * 32,
        "expires_at": "2026-10-11T00:00:00Z",
        "identity": {key: SETTINGS[key] for key in (
            "deployment_id", "tenancy_ocid", "compartment_ocid", "secret_ocid",
            "inference_region", "model_id",
        )} | {"stack_ocid": "ocid1.ormstack.oc1.iad.synthetic"},
        "model_key_ocid": "ocid1.generativeaiapikey.oc1.iad.synthetic",
        "runtime": {
            "public_ip": "8.8.4.4", "public_ip_ocid": "ocid1.publicip.oc1.iad.synthetic",
            "instance_ocid": INSTANCE,
            **{key: SETTINGS[key] for key in ("presenter_email", "external_provider", "external_model_id")},
        },
        "credentials": {
            "oci_api_key": "synthetic-oci-key", "external_api_key": "synthetic-anthropic-key",
            "database_password": "a" * 48, "gateway_master_key": "sk-" + "b" * 48,
            "gateway_salt_key": "c" * 64, "demo_password": "Synthetic9!Password",
        },
    }
