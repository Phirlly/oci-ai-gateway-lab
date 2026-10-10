"""Bounded OCI CLI failure summaries containing only fixed public error codes."""

import json

_PREFIX = 'ServiceError:\n'
_MAX_BYTES = 16 * 1024
_CODES = {
    400: {'CannotParseRequest', 'InvalidParameter', 'LimitExceeded', 'MissingParameter',
          'QuotaExceeded', 'RelatedResourceNotAuthorizedOrNotFound'},
    401: {'NotAuthenticated'},
    403: {'NotAllowed', 'NotAuthorized', 'SignUpRequired'},
    404: {'InvalidParameter', 'NotAuthorizedOrNotFound', 'NotFound', 'NamespaceNotFound'},
    405: {'MethodNotAllowed'},
    409: {'Conflict', 'ExternalServerIncorrectState', 'IncorrectState', 'InvalidatedRetryToken',
          'ResourceLocked', 'NotAuthorizedOrResourceAlreadyExists'},
    412: {'NoEtagMatch'},
    413: {'PayloadTooLarge'},
    422: {'UnprocessableEntity'},
    429: {'TooManyRequests'},
    431: {'RequestHeaderFieldsTooLarge'},
    500: {'InternalServerError'},
    501: {'MethodNotImplemented'},
    503: {'ExternalServerUnreachable', 'ExternalServerTimeout', 'ExternalServerInvalidResponse',
          'ServiceUnavailable'},
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite JSON value')


def _require_bounded_depth(value):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 16:
            raise ValueError('Nested diagnostic exceeds its bound')
        children = item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()
        pending.extend((child, depth + 1) for child in children)


def service_error_summary(stderr):
    if not isinstance(stderr, str) or len(stderr) > _MAX_BYTES or not stderr.startswith(_PREFIX):
        return None
    try:
        if len(stderr.encode('utf-8')) > _MAX_BYTES:
            return None
        value = json.loads(stderr[len(_PREFIX):], object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        _require_bounded_depth(value)
        if not isinstance(value, dict) or type(value.get('status')) is not int:
            return None
        status, code = value['status'], value.get('code')
        if not 400 <= status <= 599:
            return None
        if not isinstance(code, str) or code not in _CODES.get(status, ()):
            code = 'unavailable'
        return f'OCI service response: HTTP {status}; code {code}.'
    except (ValueError, RecursionError):
        return None
