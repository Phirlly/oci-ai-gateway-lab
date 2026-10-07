"""Small, loopback-only HTTP client for the gateway contracts."""

import base64
import json
import math
import os
import signal
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import current_thread, main_thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


@dataclass(repr=False)
class Response:
    status: int
    body: bytes = field(repr=False)
    headers: object = field(repr=False)

    def json(self):
        return json.loads(self.body)


@contextmanager
def request_deadline(seconds):
    """Bound synchronous Unix HTTP work without taking an existing caller timer."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("HTTP timeout must be positive and finite")
    if not hasattr(signal, "setitimer") or current_thread() is not main_thread():
        raise RuntimeError("HTTP contracts require a Unix main thread")
    if any(signal.getitimer(signal.ITIMER_REAL)):
        raise RuntimeError("HTTP contracts cannot replace an active timer")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise TimeoutError("Gateway request exceeded its total time budget")

    try:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def token_payload(token):
    """Extract the same outer JWT payload as the UI; the server verifies auth."""
    encoded = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


class GatewayClient:
    def __init__(self, credential=None):
        self.base_url = os.environ["GATEWAY_TEST_URL"]
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("Contracts require a loopback HTTP gateway")
        self.credential = credential
        self.opener = build_opener(ProxyHandler({}))

    def request(self, method, path, data=None, *, timeout=20):
        headers = {"Content-Type": "application/json"}
        if self.credential:
            headers["Authorization"] = "Bearer " + self.credential
        body = None if data is None else json.dumps(data).encode()
        request = Request(self.base_url + path, body, headers, method=method)
        with request_deadline(timeout):
            try:
                response = self.opener.open(request, timeout=timeout)
            except HTTPError as error:
                response = error
            except URLError as error:
                if isinstance(error.reason, TimeoutError):
                    raise TimeoutError("Gateway request timed out") from None
                raise
            with response:
                return Response(response.status, response.read(1_000_000), response.headers)


def require_status(response, expected, operation):
    if response.status != expected:
        # Never echo authentication response bodies or request credentials.
        raise AssertionError(f"{operation}: expected HTTP {expected}, got {response.status}")
    return response
