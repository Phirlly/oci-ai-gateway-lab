"""Retain only fixed rate-limit types and bounded retry guidance, never raw errors."""

import json
import math
import re

from runtime.gateway_http import GatewayError

RATE_LIMIT_TYPES = frozenset({'all_deployments_in_cooldown', 'throttling_error', 'rate_limit_error'})


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError


def _error_type(body):
    try:
        if not isinstance(body, bytes) or len(body) > 16384:
            return 'UNKNOWN'
        value = json.loads(body.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_reject_constant)
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 16 or isinstance(item, float) and not math.isfinite(item):
                return 'UNKNOWN'
            children = item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()
            pending.extend((child, depth + 1) for child in children)
        error = value.get('error') if isinstance(value, dict) else None
        kind = error.get('type') if isinstance(error, dict) else None
        return kind if isinstance(kind, str) and kind in RATE_LIMIT_TYPES else 'UNKNOWN'
    except (ValueError, UnicodeError, RecursionError):
        return 'UNKNOWN'


def _retry_seconds(headers, name):
    # HTTPMessage.items() preserves duplicate field lines; .get() would hide them.
    values = [value for key, value in headers.items() if isinstance(key, str) and key.lower() == name]
    if len(values) != 1 or not isinstance(values[0], str) or not re.fullmatch(r'[0-9]{1,4}', values[0]):
        return None
    seconds = int(values[0])
    return seconds if seconds <= 3600 else None


class ModelRouteError(GatewayError):
    def __init__(self, response):
        super().__init__(f'Model route returned HTTP {response.status}')
        self.details = None
        if response.status == 429:
            self.details = {'type': _error_type(response.body),
                            'retry_after_seconds': _retry_seconds(response.headers, 'retry-after'),
                            'provider_retry_after_seconds': _retry_seconds(response.headers, 'llm_provider-retry-after')}
