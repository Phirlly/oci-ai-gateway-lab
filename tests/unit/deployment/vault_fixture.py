"""In-memory Vault with explicit commit/lost-reply behavior for protocol tests."""

import base64
from copy import deepcopy

from deployment.credential_errors import MutationUncertain, VaultReadError
from deployment.credential_records import parse_record
from deployment.secret_delivery import SecretDelivery
from deployment.vault_state import VaultTarget
from .record_fixtures import IDENTITY, NOW, document, encoded

VAULT_ID = "ocid1.vault.oc1.iad.example"
ENCRYPTION_KEY_ID = "ocid1.key.oc1.iad.example"


def record(kind="runtime-bundle", **changes):
    value = document(kind)
    value.update(changes)
    return parse_record(encoded(value), IDENTITY)


class MemoryVault:
    def __init__(self):
        self.current = 1
        self.etag = 1
        self.rows = {1: ("unconfigured", b"UNCONFIGURED")}
        self.pending = set()
        self.mutations = []
        self.lose_stage_reply = False
        self.lose_promote_reply = False
        self.reject_stage = False
        self.before_promote = None
        self.metadata_overrides = {}

    def add(self, value, *, current=False):
        number = len(self.rows) + 1
        self.rows[number] = (value.version_name, value.content)
        self.pending.add(number)
        if current:
            self.current = number
            self.pending.discard(number)
        self.etag += 1
        return number

    def metadata(self, secret_id):
        data = {
            "id": secret_id, "compartment-id": IDENTITY["compartment_ocid"],
            "vault-id": VAULT_ID, "key-id": ENCRYPTION_KEY_ID,
            "lifecycle-state": "ACTIVE", "current-version-number": self.current,
            "freeform-tags": {"solution": "oci-ai-gateway-lab", "deployment_id": "gateway-test"},
        }
        data.update(deepcopy(self.metadata_overrides))
        return {"etag": str(self.etag), "data": data}

    def stages(self, number):
        if number == self.current:
            return ["CURRENT"]
        return ["PENDING"] if number in self.pending else ["DEPRECATED"]

    def versions(self, secret_id):
        return {"data": [
            {"secret-id": secret_id, "name": name, "version-number": number,
             "stages": self.stages(number)}
            for number, (name, _) in self.rows.items()
        ]}

    def bundle(self, secret_id, *, version_number=None, version_name=None):
        if version_name is not None:
            matches = [number for number, row in self.rows.items() if row[0] == version_name]
            if len(matches) != 1:
                raise VaultReadError("Exact version unavailable.")
            version_number = matches[0]
        name, content = self.rows[version_number]
        return {"data": {
            "secret-id": secret_id, "version-number": version_number,
            "version-name": name, "stages": self.stages(version_number),
            "secret-bundle-content": {
                "content-type": "BASE64",
                "content": base64.b64encode(content).decode("ascii"),
            },
        }}

    def stage(self, secret_id, version_name, content, etag):
        self.mutations.append(("stage", version_name, etag))
        if self.reject_stage or etag != str(self.etag):
            raise MutationUncertain("Synthetic lost/rejected request.")
        value = parse_record(content, IDENTITY)
        assert value.version_name == version_name
        self.add(value)
        if self.lose_stage_reply:
            raise MutationUncertain("Synthetic lost reply.")
        return {"data": {}}

    def promote(self, secret_id, version_number, etag):
        self.mutations.append(("promote", version_number, etag))
        if self.before_promote:
            self.before_promote(self)
        if etag != str(self.etag):
            raise MutationUncertain("Synthetic precondition failure.")
        self.current = version_number
        self.pending.discard(version_number)
        self.etag += 1
        if self.lose_promote_reply:
            raise MutationUncertain("Synthetic lost reply.")
        return {"data": {}}


def delivery(vault):
    target = VaultTarget(IDENTITY, VAULT_ID, ENCRYPTION_KEY_ID)
    return SecretDelivery(vault, target, now=lambda: NOW)
