"""Loopback fixture using the production gateway HTTP boundary."""

import os

from runtime.gateway_http import Response, GatewayHTTP, request_deadline, token_payload


class GatewayClient(GatewayHTTP):
    def __init__(self, credential=None):
        super().__init__(os.environ["GATEWAY_TEST_URL"], credential, allow_loopback=True)


def require_status(response, expected, operation):
    if response.status != expected:
        # Never echo authentication response bodies or request credentials.
        raise AssertionError(f"{operation}: expected HTTP {expected}, got {response.status}")
    return response
