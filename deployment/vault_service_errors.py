"""Recognize only proven conditional rejection of named credential staging."""

import json
import re

from .credential_identity import valid_ocid
from .oci_service_errors import service_error_summary

_FIELDS = {'secretId', 'ifMatch', 'secretContentName', 'secretContentStage', 'secretContentContent'}


def staging_etag_rejected(stderr, content):
    # The existing diagnostic parser rejects duplicate, nonfinite, deep,
    # contaminated and oversized error documents before we inspect any message.
    summary = service_error_summary(stderr)
    if summary not in ('OCI service response: HTTP 409; code Conflict.',
                       'OCI service response: HTTP 412; code NoEtagMatch.'):
        return False
    try:
        if not isinstance(content, str) or len(content) > 32768:
            return False
        request = json.loads(content)
        if not isinstance(request, dict) or set(request) != _FIELDS:
            return False
        secret, etag, name = request['secretId'], request['ifMatch'], request['secretContentName']
        if (not valid_ocid(secret, 'vaultsecret') or not isinstance(etag, str)
                or re.fullmatch(r'[!-~]{1,256}', etag) is None
                or not isinstance(name, str) or re.fullmatch(r'(intent|runtime)-[a-f0-9]{32}', name) is None
                or request['secretContentStage'] != 'PENDING'
                or not isinstance(request['secretContentContent'], str) or not request['secretContentContent']):
            return False
        if summary == 'OCI service response: HTTP 412; code NoEtagMatch.':
            return True
        message = json.loads(stderr[len('ServiceError:\n'):]).get('message')
        if not isinstance(message, str):
            return False
        match = re.fullmatch(
            re.escape(f'Entity Secret with ID {secret} has a computed tag of ')
            + r'([!-~]{1,256})'
            + re.escape(f', but is passed a tag of {etag}'), message,
        )
        return match is not None and match[1] != etag
    except (ValueError, TypeError, RecursionError):
        return False
