"""A conditional rejection changes metadata but never commits requested bytes."""

from deployment.credential_errors import VaultETagConflict
from deployment.credential_records import parse_record
from .record_fixtures import IDENTITY
from .vault_fixture import MemoryVault


class ETagRejectingVault(MemoryVault):
    def __init__(self):
        super().__init__()
        self.reject_kind = 'runtime-bundle'
        self.rejections_remaining = 1
        self.after_rejection = lambda: None
        self.attempts = []

    def stage(self, secret_id, version_name, content, etag):
        self.attempts.append((secret_id, version_name, content, etag))
        record = parse_record(content, IDENTITY)
        if record.kind == self.reject_kind and self.rejections_remaining:
            self.rejections_remaining -= 1
            self.etag += 1
            self.after_rejection()
            raise VaultETagConflict('Conditional upload rejected.')
        return super().stage(secret_id, version_name, content, etag)
