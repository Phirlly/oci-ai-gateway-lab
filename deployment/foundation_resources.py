"""Resolve credential destinations from an attested Apply's typed inventory."""

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .vault_state import VaultTarget

RESOURCE_KINDS = {
    'oci_kms_vault.runtime': ('oci_kms_vault', 'vault'),
    'oci_kms_key.runtime': ('oci_kms_key', 'key'),
    'oci_vault_secret.runtime': ('oci_vault_secret', 'vaultsecret'),
}


def resource_ids(response, config, resource_kinds):
    """Caller must first attest successful job inputs and package contents."""
    try:
        data = response['data']
        rows = data['items']
        if (not isinstance(rows, list) or len(rows) > 256
                or any(container.get(key) for container in (response, data)
                       for key in ('opc-next-page', 'next-page'))):
            raise ValueError
        found, seen = {}, set()
        for row in rows:
            address = row['resource-address']
            if (not isinstance(address, str) or not address or address in seen
                    or not isinstance(row['resource-type'], str) or not row['resource-type']
                    or not isinstance(row['resource-id'], str) or not row['resource-id']):
                raise ValueError
            seen.add(address)
            if address not in resource_kinds:
                continue
            resource_type, ocid_kind = resource_kinds[address]
            if (row['resource-type'] != resource_type
                    or not valid_ocid(row['resource-id'], ocid_kind)
                    or row['region'] != config.values['region']):
                raise ValueError
            found[address] = row['resource-id']
        if set(found) != set(resource_kinds):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError('Complete foundation resource identity could not be verified.') from None
    return found


def vault_target(response, config, stack_id, inference_region):
    """Caller must verify job success, captured inputs and package first."""
    found = resource_ids(response, config, RESOURCE_KINDS)
    settings = config.values
    identity = {
        'deployment_id': settings['deployment_id'], 'tenancy_ocid': settings['tenancy_ocid'],
        'compartment_ocid': settings['compartment_ocid'], 'stack_ocid': stack_id,
        'secret_ocid': found['oci_vault_secret.runtime'],
        'inference_region': inference_region, 'model_id': settings['oci_model_id'],
    }
    return VaultTarget(identity, found['oci_kms_vault.runtime'], found['oci_kms_key.runtime'])
