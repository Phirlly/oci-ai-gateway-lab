"""Successful Destroy is reported removed only with empty managed state."""

import json
import unittest

from deployment.removed_state import require_no_managed_resources
from deployment.credential_errors import DeliveryError


class RemovedStateTests(unittest.TestCase):
    def state(self, resources):
        return json.dumps({'version': 4, 'serial': 8, 'lineage': 'synthetic', 'resources': resources}).encode()

    def test_empty_state_or_retained_data_sources_prove_no_managed_resources(self):
        require_no_managed_resources(self.state([]))
        require_no_managed_resources(self.state([{'mode': 'data', 'instances': [{}]}]))

    def test_retained_instance_and_deposed_instance_both_block_removal_claim(self):
        for instance in ({'attributes': {}}, {'deposed': 'old', 'attributes': {}}):
            with self.subTest(instance=instance), self.assertRaises(DeliveryError):
                require_no_managed_resources(self.state([{'mode': 'managed', 'instances': [instance]}]))

    def test_malformed_unknown_version_or_incomplete_resources_fail_closed(self):
        for content in (b'{}', b'not-json', b'{"version":true,"resources":[]}',
                        b'{"version":4,"resources":null}', self.state([{}]),
                        self.state([{'mode': 'other', 'instances': []}])):
            with self.subTest(content=content), self.assertRaises(DeliveryError):
                require_no_managed_resources(content)
