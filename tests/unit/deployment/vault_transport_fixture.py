"""Exercise the real VaultCLI retry policy against the existing memory service."""

import base64

from deployment.vault_cli import VaultCLI
from deployment.credential_errors import VaultReadError
from .record_fixtures import IDENTITY


class MemoryVaultTransport(VaultCLI):
    def __init__(self, service):
        # No real child process or credentials: only the request boundary is fake.
        self.service = service
        self.region = IDENTITY["inference_region"]
        self.calls = []
        self.fail_when = lambda command, payload: False
        self.failures_remaining = 0

    def request(self, command, payload, *, mutation=False):
        self.calls.append((command, dict(payload), mutation))
        if not mutation and self.failures_remaining and self.fail_when(command, payload):
            self.failures_remaining -= 1
            raise VaultReadError("synthetic-secret-sentinel")
        secret = payload["secretId"]
        if command[:3] == ("vault", "secret", "get"):
            return self.service.metadata(secret)
        if command[:3] == ("vault", "secret-version", "list"):
            return self.service.versions(secret)
        if command[:3] == ("secrets", "secret-bundle", "get"):
            return self.service.bundle(secret, version_number=payload.get("versionNumber"),
                                       version_name=payload.get("secretVersionName"))
        if command[:3] == ("vault", "secret", "update-base64"):
            return self.service.stage(secret, payload["secretContentName"],
                                      base64.b64decode(payload["secretContentContent"]),
                                      payload["ifMatch"])
        if command[:3] == ("vault", "secret", "update"):
            return self.service.promote(secret, payload["currentVersionNumber"], payload["ifMatch"])
        raise AssertionError("Unexpected synthetic command")
