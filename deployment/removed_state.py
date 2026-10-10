"""Inspect only resource counts from an exact successful Destroy's private state."""

import json

from .credential_errors import DeliveryError
from .credential_records import _unique_object
from .foundation_package import MAX_ARCHIVE_BYTES


def require_no_managed_resources(content):
    try:
        if not isinstance(content, bytes) or not 0 < len(content) <= MAX_ARCHIVE_BYTES:
            raise ValueError
        value = json.loads(content, object_pairs_hook=_unique_object)
        if not isinstance(value, dict) or type(value['version']) is not int or value['version'] != 4:
            raise ValueError
        resources = value['resources']
        if not isinstance(resources, list) or len(resources) > 256:
            raise ValueError
        for resource in resources:
            if resource['mode'] not in ('managed', 'data') or not isinstance(resource['instances'], list):
                raise ValueError
            if resource['mode'] == 'managed' and resource['instances']:
                raise ValueError
    except (ValueError, TypeError, KeyError, RecursionError):
        raise DeliveryError('Destroy state does not prove zero remaining managed resources; inspect the exact job privately.') from None
