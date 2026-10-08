"""Fixed Generative AI key commands; creation never uses a waiter."""

from .oci_cli import OCICommand


class ModelKeysCLI(OCICommand):
    def create(self, request):
        return self.request(("generative-ai", "api-key", "create"), request, mutation=True)

    def get(self, key_id):
        return self.request(("generative-ai", "api-key", "get"), {"apiKeyId": key_id})

    def list(self, compartment_id):
        return self.request(
            ("generative-ai", "api-key-collection", "list-api-keys", "--all"),
            {"compartmentId": compartment_id},
        )
