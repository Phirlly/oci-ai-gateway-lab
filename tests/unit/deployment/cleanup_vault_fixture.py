"""Named cleanup versions with real PENDING displacement and lost replies."""

from types import SimpleNamespace

from deployment.credential_errors import MutationUncertain
from .vault_fixture import MemoryVault


class CleanupMemoryVault(MemoryVault):
    def stage(self, secret_id, version_name, content, etag):
        self.mutations.append(('stage', version_name, etag))
        if self.reject_stage or etag != str(self.etag) or len(version_name) > 50:
            raise MutationUncertain('Synthetic unconfirmed upload')
        self.pending.clear()
        self.add(SimpleNamespace(version_name=version_name, content=content))
        if self.lose_stage_reply:
            raise MutationUncertain('Synthetic lost upload reply')
