"""Create a model key once, save it immediately, and verify it before binding."""

import json

from .credential_creation import prepare_credentials, runtime_record
from .credential_errors import DeliveryError, MutationUncertain
from .model_key_state import owned_candidates, parse_model_key
from .vault_state import read_version


class ModelKeyProvisioner:
    def __init__(self, delivery, keys):
        self.delivery = delivery
        self.keys = keys
        if keys.region != delivery.target.identity["inference_region"]:
            raise DeliveryError("Model-key client must use the deployment inference region.")

    def _discover(self):
        identity = dict(self.delivery.target.identity)
        return owned_candidates(self.keys.list(identity["compartment_ocid"]), identity)

    def _ready(self, receipt):
        version = read_version(
            self.delivery.client, self.delivery.target, self.delivery.now(),
            number=receipt.version_number,
        )
        if (
            receipt.phase not in {"CURRENT", "PENDING"}
            or version.name != receipt.version_name or version.record is None
            or version.record.kind != "runtime-bundle"
            or version.record.model_key_ocid != receipt.model_key_ocid
            or receipt.phase not in version.stages
        ):
            raise DeliveryError("Saved runtime binding changed; reconcile before proceeding.")
        parse_model_key(
            self.keys.get(receipt.model_key_ocid), version.record,
            now=self.delivery.now(), expected_key_id=receipt.model_key_ocid,
            require_active=True,
        )
        current = self.delivery.reconcile(receipt.model_key_ocid)
        if current.version_name != receipt.version_name or current.version_number != receipt.version_number:
            raise DeliveryError("Runtime version changed during key verification.")
        return current

    def prepare(self, *, external_api_key=None, demo_password=None,
                expires_at=None, stack_key_ocid=None):
        receipt = self.delivery.reconcile(stack_key_ocid)
        if receipt.phase in {"CURRENT", "PENDING"}:
            return self._ready(receipt)
        if receipt.phase == "INTENT":
            self._discover()
            raise DeliveryError("A recorded key-creation intent requires explicit recovery; no key was retried.")
        if receipt.phase != "UNCONFIGURED":
            raise DeliveryError("Unexpected credential phase; explicit recovery is required.")
        draft = prepare_credentials(
            dict(self.delivery.target.identity), external_api_key, demo_password,
            expires_at, now=self.delivery.now(),
        )
        if self._discover():
            raise DeliveryError("Existing model keys without a runtime bundle require explicit recovery.")
        claim = self.delivery.stage(draft.intent, fresh_intent=True)
        if claim.phase == "CURRENT":
            return self._ready(claim)
        if claim.phase != "INTENT" or claim.version_name != draft.intent.version_name:
            raise DeliveryError("Fresh creation intent could not be confirmed; recovery is required.")
        # Freshness comes from this invocation AND the confirmed new upload.
        # Never resume creation merely because a durable intent is readable.
        try:
            response = self.keys.create(json.loads(draft.intent.content)["request"])
        except MutationUncertain:
            raise DeliveryError("Model-key creation is uncertain; recover the recorded intent before retry.") from None
        key = parse_model_key(response, draft.intent, now=self.delivery.now(), require_secret=True)
        runtime = runtime_record(draft, key.key_id, key.secret)
        staged = self.delivery.stage(runtime)
        if staged.model_key_ocid != key.key_id or staged.version_name != runtime.version_name:
            raise DeliveryError("Runtime staging conflicts with existing credentials; recovery is required.")
        return self._ready(staged)
