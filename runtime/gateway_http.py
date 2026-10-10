"""Bounded gateway API calls over verified HTTPS or explicit bootstrap loopback."""

import base64
import binascii
import json
import math
import signal
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.client import HTTPException
from ipaddress import IPv4Address
from threading import current_thread, main_thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_BODY_BYTES = 1_000_000


class GatewayError(ValueError):
    """Sanitized failure; never includes request or response content."""


@dataclass(repr=False)
class Response:
    status: int
    body: bytes = field(repr=False)
    headers: object = field(repr=False)

    def json(self):
        try:
            return json.loads(self.body)
        except (ValueError, RecursionError):
            raise GatewayError("Gateway returned invalid JSON") from None


@contextmanager
def request_deadline(seconds):
    """Bound synchronous Unix HTTP work without taking an existing caller timer."""
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 120:
        raise ValueError("HTTP timeout must be positive, finite and at most 120 seconds")
    if not hasattr(signal, "setitimer") or current_thread() is not main_thread():
        raise RuntimeError("Gateway HTTP requires a Unix main thread")
    if any(signal.getitimer(signal.ITIMER_REAL)):
        raise RuntimeError("Gateway HTTP cannot replace an active timer")
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
    """Read the UI's outer JWT; the gateway verifies the contained session key."""
    try:
        if not isinstance(token, str) or not 0 < len(token) <= 32768:
            raise ValueError
        parts = token.split(".")
        if len(parts) != 3 or not all(parts):
            raise ValueError
        encoded = parts[1]
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (ValueError, binascii.Error, RecursionError):
        raise GatewayError("Gateway returned an invalid session token") from None


def session_key(token):
    key = token_payload(token).get("key")
    if not _valid_credential(key):
        raise GatewayError("Gateway returned an invalid session key")
    return key


def _valid_credential(value):
    return (isinstance(value, str) and 0 < len(value) <= 16384
            and all(33 <= ord(c) <= 126 for c in value))


def _validate_origin(base_url, allow_loopback):
    try:
        if not isinstance(base_url, str) or any(ord(c) < 33 or ord(c) > 126 for c in base_url):
            raise ValueError
        parsed = urlsplit(base_url)
        address = IPv4Address(parsed.hostname)
        origin = parsed.scheme + "://" + str(address)
        if parsed.port is not None:
            origin += ":" + str(parsed.port)
        if base_url != origin:
            raise ValueError
        public = (parsed.scheme == "https" and address.is_global
                  and not address.is_multicast and parsed.port in (None, 443))
        local = (allow_loopback and parsed.scheme == "http" and str(address) == "127.0.0.1"
                 and (parsed.port is None or 0 < parsed.port <= 65535))
        if not (public or local):
            raise ValueError
    except (ValueError, TypeError):
        raise GatewayError("Gateway requires public IPv4 HTTPS or explicit loopback HTTP") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirect rejected", headers, fp)


class GatewayHTTP:
    def __init__(self, base_url, credential=None, *, allow_loopback=False):
        _validate_origin(base_url, allow_loopback)
        if credential is not None and not _valid_credential(credential):
            raise GatewayError("Invalid gateway credential")
        self.base_url, self.credential = base_url, credential
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def request(self, method, path, data=None, *, timeout=20):
        if (method not in ("GET", "POST") or not isinstance(path, str)
                or not path.startswith("/") or path.startswith("//") or len(path) > 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in path) or "#" in path):
            raise GatewayError("Invalid gateway request path or method")
        headers = {"Content-Type": "application/json"}
        if self.credential:
            headers["Authorization"] = "Bearer " + self.credential
        try:
            body = None if data is None else json.dumps(data, allow_nan=False).encode()
            if body is not None and len(body) > MAX_BODY_BYTES:
                raise ValueError
        except (TypeError, ValueError, RecursionError):
            raise GatewayError("Invalid gateway request body") from None
        request = Request(self.base_url + path, body, headers, method=method)
        with request_deadline(timeout):
            try:
                try:
                    response = self.opener.open(request, timeout=timeout)
                except HTTPError as error:
                    response = error
                with response:
                    content = response.read(MAX_BODY_BYTES + 1)
                    if len(content) > MAX_BODY_BYTES:
                        raise GatewayError("Gateway response exceeded its size limit")
                    length = response.headers.get("Content-Length")
                    if length is not None and (not length.isdecimal() or int(length) != len(content)):
                        raise GatewayError("Gateway response was incomplete")
                    return Response(response.status, content, response.headers)
            except TimeoutError:
                raise TimeoutError("Gateway request timed out") from None
            except URLError as error:
                if isinstance(error.reason, TimeoutError):
                    raise TimeoutError("Gateway request timed out") from None
                raise GatewayError("Gateway connection could not be verified") from None
            except (OSError, HTTPException):
                raise GatewayError("Gateway response could not be read") from None
