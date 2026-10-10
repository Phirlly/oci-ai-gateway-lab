"""Strict private cleanup manifests and deterministic per-key terminal receipts."""

import json
import re

from .credential_errors import DeliveryError
from .credential_identity import valid_ocid
from .submission_records import digest


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def manifest_context(store, package_hash, config_hash):
    if any(not isinstance(value, str) or re.fullmatch('[a-f0-9]{64}', value) is None
           for value in (package_hash, config_hash)):
        raise DeliveryError('Original package and configuration hashes are required for cleanup.')
    return {'schema_version': 1, 'kind': 'cleanup-manifest', 'identity': dict(store.target.identity),
            'operation_id': store.operation, 'package_hash': package_hash, 'config_hash': config_hash}


def parse_manifest(content, context):
    try:
        value = json.loads(content)
        if (not isinstance(value, dict) or set(value) != set(context) | {'keys'}
                or any(value[k] != v or type(value[k]) is not type(v) for k, v in context.items())
                or encoded(value) != content or not isinstance(value['keys'], list) or len(value['keys']) > 16):
            raise ValueError
        identifiers = set()
        for row in value['keys']:
            if (not isinstance(row, dict) or set(row) != {'key_id', 'operation_id'}
                    or not valid_ocid(row['key_id'], 'generativeaiapikey')
                    or row['key_id'] in identifiers or not isinstance(row['operation_id'], str)
                    or re.fullmatch('[a-f0-9]{32}', row['operation_id']) is None):
                raise ValueError
            identifiers.add(row['key_id'])
        return value
    except (ValueError, KeyError, TypeError, RecursionError):
        raise DeliveryError('Cleanup manifest does not match the original owned deployment.') from None


def key_receipt(store, manifest, identifier):
    # Vault version names are limited to 50 characters; hash the full identity.
    name = 'removed-' + digest([store.operation, identifier])[:32]
    content = encoded({'schema_version': 1, 'kind': 'key-removed',
                       'manifest_hash': digest(manifest), 'key_id': identifier})
    return name, content


def legacy_receipt_name(store, identifier):
    """Recognize retained evidence without emitting the older oversized name."""
    return 'removed-' + store.operation + '-' + digest(identifier)[:32]
