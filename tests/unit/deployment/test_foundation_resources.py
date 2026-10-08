"""Only exact typed job resources may identify the credential destination."""

import unittest

from deployment.credential_errors import DeliveryError
from deployment.deployment_config import FoundationConfig
from deployment.foundation_resources import vault_target
from .inventory_fixture import inventory
from .orm_fixtures import SETTINGS, STACK_ID
from .record_fixtures import IDENTITY
from .vault_fixture import VAULT_ID, ENCRYPTION_KEY_ID


class FoundationResourceTests(unittest.TestCase):
    def parse(self, response):
        return vault_target(response, FoundationConfig(SETTINGS), STACK_ID,
                            IDENTITY['inference_region'])

    def test_exact_addresses_produce_complete_deployment_identity(self):
        result = self.parse(inventory())
        self.assertEqual(dict(result.identity), IDENTITY)
        self.assertEqual((result.vault_ocid, result.key_ocid), (VAULT_ID, ENCRYPTION_KEY_ID))

    def test_other_home_region_resources_do_not_change_destination(self):
        response = inventory()
        response['data']['items'].append({
            'resource-address': 'oci_identity_policy.model[0]',
            'resource-type': 'oci_identity_policy', 'resource-id': 'ocid1.policy.oc1..example',
            'region': 'us-phoenix-1',
        })
        self.assertEqual(self.parse(response), self.parse(inventory()))

    def test_missing_duplicate_or_renamed_required_address_stops(self):
        missing, duplicate, renamed = inventory(), inventory(), inventory()
        missing['data']['items'].pop()
        duplicate['data']['items'].append(duplicate['data']['items'][0])
        renamed['data']['items'][0]['resource-address'] = 'oci_kms_vault.other'
        for response in (missing, duplicate, renamed):
            with self.subTest(response=response), self.assertRaises(DeliveryError):
                self.parse(response)

    def test_wrong_resource_type_kind_or_region_stops(self):
        for field, value in (
            ('resource-type', 'oci_kms_key'), ('resource-id', ENCRYPTION_KEY_ID),
            ('resource-id', None), ('region', 'us-chicago-1'), ('region', None),
        ):
            response = inventory()
            response['data']['items'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DeliveryError):
                self.parse(response)

    def test_partial_or_malformed_collection_stops(self):
        responses = [None, {}, {'data': []}, {'data': {'items': None}},
                     {'data': {'items': []}}, {'data': {'items': [None]}},
                     {'data': {'items': [{}]}},
                     {'data': {'items': inventory()['data']['items'] * 100}}]
        for key in ('opc-next-page', 'next-page'):
            responses.append(inventory() | {key: 'more'})
        nested = inventory()
        nested['data']['opc-next-page'] = 'more'
        responses.append(nested)
        for response in responses:
            with self.subTest(response=str(response)[:60]), self.assertRaises(DeliveryError):
                self.parse(response)
