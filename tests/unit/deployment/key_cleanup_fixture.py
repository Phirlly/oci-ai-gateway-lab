"""Metadata-only key service with explicit deletion acknowledgments."""

from copy import deepcopy

from deployment.credential_errors import MutationUncertain
from .model_key_fixture import key_data
from .record_fixtures import IDENTITY


class CleanupKeys:
    region = IDENTITY['inference_region']

    def __init__(self):
        self.rows = [key_data()]
        self.deleted = []
        self.get_changes = {}
        self.lose_reply = False
        self.commit_delete = True
        self.etag = 'version-one'

    def list(self, compartment):
        return {'data': {'items': deepcopy(self.rows)}}

    def get(self, identifier):
        row = deepcopy(next(row for row in self.rows if row['id'] == identifier))
        row.update(deepcopy(self.get_changes))
        return {'data': row, 'etag': self.etag}

    def delete(self, identifier, etag):
        self.deleted.append((identifier, etag))
        if self.commit_delete:
            next(row for row in self.rows if row['id'] == identifier)['lifecycle-state'] = 'DELETED'
        if self.lose_reply or not self.commit_delete:
            raise MutationUncertain('Synthetic unconfirmed deletion.')
