"""Identity shared by typed Vault records and their deployment owner."""

import re

IDENTITY_FIELDS = {
    "deployment_id", "tenancy_ocid", "compartment_ocid", "stack_ocid",
    "secret_ocid", "inference_region", "model_id",
}
OCID_TYPES = {
    "tenancy_ocid": "tenancy", "compartment_ocid": "compartment",
    "stack_ocid": "ormstack", "secret_ocid": "vaultsecret",
}


def valid_ocid(value, resource):
    region = "" if resource in {"tenancy", "compartment", "user"} else "[a-z0-9-]+"
    pattern = rf"ocid1\.{resource}\.oc1\.{region}\.[a-zA-Z0-9._-]+"
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def valid_identity(value):
    if not isinstance(value, dict) or set(value) != IDENTITY_FIELDS:
        return False
    if not all(valid_ocid(value[key], kind) for key, kind in OCID_TYPES.items()):
        return False
    patterns = {
        "deployment_id": r"[a-z][a-z0-9-]{2,39}",
        "inference_region": r"[a-z]{2,}-[a-z0-9-]+-[0-9]+",
        "model_id": r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,254}",
    }
    return all(
        isinstance(value[key], str) and re.fullmatch(pattern, value[key])
        for key, pattern in patterns.items()
    )
