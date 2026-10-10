"""Synthetic complete deployment settings; no customer identifiers."""

from .orm_fixtures import SETTINGS

GATEWAY_SETTINGS = {
    **SETTINGS,
    "schema_version": 2,
    "inference_region": "us-ashburn-1",
    "external_provider": "anthropic",
    "external_model_id": "claude-sonnet-4-6",
    "presenter_email": "presenter@example.test",
    "instance_shape": "VM.Standard.E5.Flex",
    "instance_ocpus": 2,
    "instance_memory_gbs": 16,
    "boot_volume_size_gbs": 80,
    "availability_domain_number": 1,
    "image_name": "Canonical-Ubuntu-24.04-2026.09.18-0",
    "model_key_ttl_days": 7,
}

CONTEXT = {
    "public_ip": "8.8.4.4",
    "public_ip_ocid": "ocid1.publicip.oc1.iad.example",
    "instance_ocid": "ocid1.instance.oc1.iad.example",
    "presenter_email": "presenter@example.test",
    "external_provider": "anthropic",
    "external_model_id": "claude-sonnet-4-6",
}
