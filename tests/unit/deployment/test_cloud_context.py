"""Only the exact attested VM and its primary address may receive credentials."""

import unittest

from deployment.cloud_context import resolve_runtime_context
from deployment.credential_errors import DeliveryError
from deployment.gateway_config import GatewayConfig
from .cloud_inventory_fixture import CloudMetadata, cloud_inventory
from .gateway_config_fixture import CONTEXT, GATEWAY_SETTINGS


class CloudContextTests(unittest.TestCase):
    def setUp(self):
        self.client = CloudMetadata()
        self.resources = cloud_inventory()

    def resolve(self):
        return resolve_runtime_context(self.client, self.resources, GatewayConfig(GATEWAY_SETTINGS))

    def test_exact_primary_address_resolves_and_stopped_vm_remains_identifiable(self):
        for state in ('RUNNING', 'STOPPED', 'STOPPING', 'STARTING', 'PROVISIONING'):
            self.client.instance['lifecycle-state'] = state
            with self.subTest(state=state):
                self.assertEqual(self.resolve(), CONTEXT)

    def test_missing_or_duplicate_attested_identity_cannot_be_substituted(self):
        self.resources['data']['items'].pop()
        with self.assertRaises(DeliveryError):
            self.resolve()
        self.resources = cloud_inventory()
        self.resources['data']['items'].append(self.resources['data']['items'][-1])
        with self.assertRaises(DeliveryError):
            self.resolve()

    def test_wrong_owner_state_address_or_subnet_fails_closed(self):
        for resource, field, value in (
            ('instance', 'id', 'foreign'), ('instance', 'compartment-id', 'foreign'),
            ('instance', 'freeform-tags', {}), ('instance', 'lifecycle-state', 'TERMINATED'),
            ('instance', 'region', 'phx'), ('public', 'scope', 'AVAILABILITY_DOMAIN'),
            ('public', 'assigned-entity-type', 'NAT_GATEWAY'), ('public', 'lifetime', 'EPHEMERAL'),
            ('public', 'lifecycle-state', 'AVAILABLE'), ('public', 'ip-address', '127.0.0.1'),
            ('private', 'is-primary', False), ('private', 'subnet-id', 'foreign'),
            ('vnic', 'subnet-id', 'foreign'), ('vnic', 'private-ip', '10.42.0.3'),
            ('vnic', 'freeform-tags', {}), ('vnic', 'public-ip', '8.8.8.8'),
        ):
            self.client = CloudMetadata()
            getattr(self.client, resource)[field] = value
            with self.subTest(resource=resource, field=field), self.assertRaises(DeliveryError):
                self.resolve()

    def test_attachment_must_prove_same_instance_vnic_and_compartment(self):
        for field, value in (('instance-id', 'foreign'), ('vnic-id', 'foreign'),
                             ('compartment-id', 'foreign'), ('lifecycle-state', 'DETACHED')):
            self.client = CloudMetadata()
            self.client.attachments[0][field] = value
            with self.subTest(field=field), self.assertRaises(DeliveryError):
                self.resolve()
        self.client.attachments = []
        with self.assertRaises(DeliveryError):
            self.resolve()
