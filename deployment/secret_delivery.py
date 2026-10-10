"""Stage and publish credentials without rotating committed content."""

from dataclasses import dataclass
from datetime import datetime, timezone
import time

from .credential_errors import DeliveryError, MutationUncertain, VaultETagConflict
from .credential_records import parse_record
from .vault_state import read_current, read_staged, read_version


@dataclass(frozen=True)
class HandoffReceipt:
    phase: str
    version_name: str
    version_number: int
    model_key_ocid: str | None


def _receipt(version, phase=None):
    record = version.record
    if phase is None:
        phase = "INTENT" if record.kind == "creation-intent" else "PENDING"
    return HandoffReceipt(
        phase, version.name, version.number, record.model_key_ocid if record else None
    )


class SecretDelivery:
    def __init__(self, client, target, *, now=None):
        self.client = client
        self.target = target
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _current(self):
        return read_current(self.client, self.target, self.now())

    def _staged(self):
        return read_staged(self.client, self.target, self.now())

    def reconcile(self, stack_key_ocid=None):
        current = self._current().version
        if current.record:
            result = _receipt(current, "CURRENT")
        else:
            pending = self._staged()
            runtime = [version for version in pending if version.record.kind == "runtime-bundle"]
            selected = runtime or pending
            result = _receipt(selected[0]) if selected else _receipt(current, "UNCONFIGURED")
        if stack_key_ocid is not None and stack_key_ocid != result.model_key_ocid:
            raise DeliveryError("Stack and durable model-key binding conflict; recovery is required.")
        return result

    def stage(self, record, *, fresh_intent=False):
        # Only a positively rejected conditional upload permits another attempt.
        # Each attempt must repeat all ownership/history checks, not just GET an ETag.
        for delay in (1, 2, None):
            try:
                return self._stage_once(record, fresh_intent=fresh_intent)
            except VaultETagConflict:
                if delay is None:
                    raise DeliveryError('Vault conditional upload remained rejected; reconcile before retry.') from None
                time.sleep(delay)

    def _stage_once(self, record, *, fresh_intent):
        # Validate again at the boundary; callers cannot forge the dataclass.
        record = parse_record(record.content, dict(self.target.identity))
        if fresh_intent and record.kind != "creation-intent":
            raise DeliveryError("Only a creation intent may request a fresh claim.")
        snapshot = self._current()
        if snapshot.version.record:
            return _receipt(snapshot.version, "CURRENT")
        record.require_unexpired(self.now())
        pending = self._staged()
        for version in pending:
            if version.record.operation_id != record.operation_id:
                raise DeliveryError("Another pending credential operation requires recovery.")
            if version.name == record.version_name:
                if fresh_intent:
                    raise DeliveryError("Creation intent already exists; explicit recovery is required.")
                if version.record.content != record.content:
                    raise DeliveryError("Named pending content conflicts with this request.")
                return _receipt(version)
        if record.kind == "runtime-bundle":
            intents = [version for version in pending if version.record.kind == "creation-intent"]
            if (not intents or intents[0].record.expires_at != record.expires_at
                    or intents[0].record.runtime_context != record.runtime_context):
                raise DeliveryError("Runtime delivery requires a matching durable creation intent.")
        elif any(version.record.kind == "runtime-bundle" for version in pending):
            raise DeliveryError("Runtime credentials are already staged; reconcile before proceeding.")
        try:
            self.client.stage(
                self.target.secret_id, record.version_name, record.content, snapshot.etag
            )
        except MutationUncertain:
            if fresh_intent:
                raise DeliveryError("Intent upload is uncertain; no key may be created.") from None
            # Never retry an uncertain write. Exact readback may prove it committed.
            pass
        version = read_version(
            self.client, self.target, self.now(), name=record.version_name
        )
        if (
            version.record is None or version.record.content != record.content
            or "PENDING" not in version.stages or "CURRENT" in version.stages
        ):
            raise DeliveryError("Pending upload is unconfirmed; reconcile before retry.")
        current = self._current().version
        if current.record:
            if current.number == version.number and current.record.content == record.content:
                return _receipt(current, "CURRENT")
            raise DeliveryError("CURRENT changed during upload; preserve it and reconcile.")
        return _receipt(version)

    def publish(self, version_name, bound_key_ocid):
        """Caller must supply the binding from a verified successful ORM Apply."""
        snapshot = self._current()
        current = snapshot.version
        if current.record:
            if current.name == version_name and current.record.model_key_ocid == bound_key_ocid:
                return _receipt(current, "CURRENT")
            raise DeliveryError("Existing CURRENT credentials cannot be replaced by normal deployment.")
        pending = self._staged()
        matches = [
            version for version in pending
            if version.name == version_name and version.record.kind == "runtime-bundle"
        ]
        if len(matches) != 1 or matches[0].record.model_key_ocid != bound_key_ocid:
            raise DeliveryError("Publication requires the exact runtime version and verified model-key binding.")
        version = matches[0]
        try:
            self.client.promote(self.target.secret_id, version.number, snapshot.etag)
        except MutationUncertain:
            pass
        # Never refresh the ETag and retry. Prove this exact version is CURRENT.
        current = self._current().version
        if (
            current.number != version.number or current.record is None
            or current.record.content != version.record.content
        ):
            raise DeliveryError("Publication is unconfirmed; reconcile before retry.")
        return _receipt(current, "CURRENT")
