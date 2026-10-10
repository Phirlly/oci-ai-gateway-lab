"""Fixed Vault commands using the shared protected OCI CLI transport."""

import base64
import time

from .credential_errors import VaultReadError
from .oci_cli import OCICommand

_COMMANDS = {
    "metadata": ("vault", "secret", "get"),
    "versions": ("vault", "secret-version", "list", "--all"),
    "bundle": ("secrets", "secret-bundle", "get"),
    "stage": ("vault", "secret", "update-base64", "--force"),
    "promote": ("vault", "secret", "update", "--force"),
}
_READ_DELAYS = (2, 4, 8, 16, 30)


class VaultCLI(OCICommand):
    read_error = VaultReadError

    def _request(self, operation, payload):
        command = _COMMANDS[operation]
        if operation in {"stage", "promote"}:
            return self.request(command, payload, mutation=True)
        # An accepted Vault update can precede exact-version availability.
        # Retry only transport reads; callers still validate content and ownership.
        for attempt in range(len(_READ_DELAYS) + 1):
            try:
                return self.request(command, payload, mutation=False)
            except VaultReadError:
                if attempt == len(_READ_DELAYS):
                    raise VaultReadError("Vault read verification remained unavailable after bounded retries.") from None
                time.sleep(_READ_DELAYS[attempt])

    def metadata(self, secret_id):
        return self._request("metadata", {"secretId": secret_id})

    def versions(self, secret_id):
        return self._request("versions", {"secretId": secret_id})

    def bundle(self, secret_id, *, version_number=None, version_name=None):
        if (version_number is None) == (version_name is None):
            raise ValueError("Select exactly one secret version name or number.")
        selector = (
            {"versionNumber": version_number} if version_number is not None
            else {"secretVersionName": version_name}
        )
        return self._request("bundle", {"secretId": secret_id, **selector})

    def stage(self, secret_id, version_name, content, etag):
        return self._request("stage", {
            "secretId": secret_id,
            "secretContentContent": base64.b64encode(content).decode("ascii"),
            "secretContentName": version_name,
            "secretContentStage": "PENDING",
            "ifMatch": etag,
        })

    def promote(self, secret_id, version_number, etag):
        return self._request("promote", {
            "secretId": secret_id, "currentVersionNumber": version_number,
            "ifMatch": etag,
        })
