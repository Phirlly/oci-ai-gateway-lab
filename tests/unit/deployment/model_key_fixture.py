"""Synthetic GenAI responses and observable create/get ordering."""

import json
from copy import deepcopy

from deployment.credential_errors import MutationUncertain
from .record_fixtures import IDENTITY, KEY_ID
from .vault_fixture import record


def key_data(request=None):
    request = request or json.loads(record("creation-intent").content)["request"]
    return {
        "id": KEY_ID, "compartment-id": request["compartmentId"],
        "display-name": request["displayName"],
        "freeform-tags": dict(request["freeformTags"]),
        "lifecycle-state": "ACTIVE",
        "keys": [{"key-name": "gateway", "key": "model-sentinel",
                  "state": "ACTIVE", "time-expiry": request["keyDetails"][0]["timeExpiry"]}],
    }


class MemoryKeys:
    region = IDENTITY["inference_region"]

    def __init__(self, vault):
        self.vault = vault
        self.rows = []
        self.created = []
        self.gets = []
        self.lose_reply = False
        self.create_changes = {}
        self.read_changes = {}
        self.before_get = None

    def list(self, compartment_id):
        return {"data": {"items": deepcopy(self.rows)}}

    def create(self, request):
        # The remote call must follow a persisted intent and precede runtime.
        assert len(self.vault.rows) == 2
        assert json.loads(self.vault.rows[2][1])["kind"] == "creation-intent"
        self.created.append(deepcopy(request))
        data = key_data(request)
        data.update(deepcopy(self.create_changes))
        self.rows.append(data)
        if self.lose_reply:
            raise MutationUncertain("Synthetic lost create reply.")
        return {"data": deepcopy(data)}

    def get(self, key_id):
        self.gets.append(key_id)
        if self.before_get:
            self.before_get()
        data = deepcopy(self.rows[0])
        data.update(deepcopy(self.read_changes))
        for item in data["keys"]:
            item.pop("key", None)
        return {"data": data}
