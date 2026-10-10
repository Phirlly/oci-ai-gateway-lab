"""Bounded direct GitHub.com HTTPS; no redirects, retries or ambient credentials."""

import http.client
import json
import math
import signal
from contextlib import contextmanager
from threading import current_thread, main_thread

from .credential_errors import CloudReadError, DeliveryError, MutationUncertain

MAX_RESPONSE_BYTES = 1024 * 1024


@contextmanager
def request_deadline(seconds):
    if (not hasattr(signal, 'setitimer') or current_thread() is not main_thread()
            or any(signal.getitimer(signal.ITIMER_REAL))):
        raise DeliveryError('Journal requests require a POSIX main thread without an active timer.')
    previous = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise TimeoutError('Journal request deadline exceeded.')

    try:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Nonfinite JSON value')


class GitHubHTTP:
    def __init__(self, token, *, timeout=30):
        if (not isinstance(token, str) or not token or len(token) > 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise DeliveryError('An explicit GitHub token is required.')
        if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 60):
            raise DeliveryError('Journal timeout must be finite and at most60 seconds.')
        self._token, self.timeout = token, timeout

    def request(self, method, path, body=None, *, expected=200):
        if (method not in ('GET', 'POST') or not isinstance(path, str)
                or not path.startswith('/') or path.startswith('//')
                or any(ord(c) < 33 or ord(c) > 126 for c in path)):
            raise DeliveryError('Unsupported journal request.')
        error = MutationUncertain if method == 'POST' else CloudReadError
        connection = None
        try:
            content = None if body is None else json.dumps(body, allow_nan=False).encode()
            if content is not None and len(content) > 16384:
                raise ValueError
            with request_deadline(self.timeout):
                connection = http.client.HTTPSConnection('api.github.com', timeout=self.timeout)
                connection.set_debuglevel(0)
                connection.request(method, path, body=content, headers={
                    'Authorization': 'Bearer ' + self._token,
                    'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                    'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'oci-ai-gateway',
                })
                response = connection.getresponse()
                if response.status != expected:
                    raise ValueError
                headers = unique_object((k.lower(), v) for k, v in response.getheaders())
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError
                if 'content-length' in headers:
                    length = headers['content-length']
                    if not length.isascii() or not length.isdecimal() or int(length) != len(raw):
                        raise ValueError
                result = json.loads(raw, object_pairs_hook=unique_object,
                                    parse_constant=reject_constant)
                return result, headers
        except (OSError, ValueError, TypeError, RecursionError, http.client.HTTPException):
            raise error('GitHub journal request could not be verified; reconcile before retry.') from None
        finally:
            if connection is not None:
                connection.close()
