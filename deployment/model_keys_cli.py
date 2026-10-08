"""Fixed Generative AI key commands; creation never uses a waiter."""

import json

from .oci_cli import OCICommand


class ModelKeysCLI(OCICommand):
    def create(self, request):
        return self.request(("generative-ai", "api-key", "create"), request, mutation=True)

    def get(self, key_id):
        return self.request(("generative-ai", "api-key", "get"), {"apiKeyId": key_id})

    def delete(self, key_id, etag):
        # Only Delete may use a waiter: creation must retain the one-time key.
        self._execute(self.command + [
            'generative-ai', 'api-key', 'delete', '--force', '--wait-for-state', 'DELETED',
            '--max-wait-seconds', '20', '--wait-interval-seconds', '2',
            '--from-json', 'file:///dev/stdin',
        ], json.dumps({'apiKeyId': key_id, 'ifMatch': etag}), mutation=True)

    def list(self, compartment_id):
        return self.request(
            ("generative-ai", "api-key-collection", "list-api-keys", "--all"),
            {"compartmentId": compartment_id},
        )
