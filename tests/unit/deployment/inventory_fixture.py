"""Typed job-resource collection using only synthetic identifiers."""

from .orm_fixtures import SETTINGS
from .record_fixtures import IDENTITY
from .vault_fixture import VAULT_ID, ENCRYPTION_KEY_ID


def inventory():
    resources = (
        ('oci_kms_vault', VAULT_ID),
        ('oci_kms_key', ENCRYPTION_KEY_ID),
        ('oci_vault_secret', IDENTITY['secret_ocid']),
    )
    return {'data': {'items': [
        {'resource-address': kind + '.runtime', 'resource-type': kind,
         'resource-id': identifier, 'region': SETTINGS['region']}
        for kind, identifier in resources
    ]}}
