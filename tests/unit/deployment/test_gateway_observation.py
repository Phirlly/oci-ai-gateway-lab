"""Status locates only attested jobs and never performs model or cloud mutations."""

import unittest
from pathlib import Path

from deployment.gateway_observation import observe_gateway
from deployment.credential_errors import DeliveryError
from deployment.foundation_package import GatewayPackage
from deployment.gateway_config import GatewayConfig
from deployment.resource_manager_stacks import StackTarget
from .cloud_inventory_fixture import CloudMetadata, cloud_inventory
from .gateway_config_fixture import GATEWAY_SETTINGS, CONTEXT
from .handoff_fixture import HandoffFixture
from .record_fixtures import IDENTITY
from .record_fixtures import EXPIRES


class GatewayObservationTests(unittest.TestCase):
    def setUp(self):
        self.f = HandoffFixture()
        self.f.target = StackTarget(GatewayConfig({**GATEWAY_SETTINGS, 'inference_region': IDENTITY['inference_region']}),
                                    self.f.target.controller_id)
        self.f.package = GatewayPackage.build(Path(__file__).resolve().parents[3])
        self.f.orm.package = self.f.package
        self.compute = CloudMetadata()

    def observe(self):
        f = self.f
        return observe_gateway(f.orm, f.journal, f.target, f.package, self.compute)

    def test_new_scope_is_not_deployed_without_creating_any_resource(self):
        self.assertEqual(self.observe().phase, 'NOT_DEPLOYED')
        self.assertFalse(self.f.orm.stacks)
        self.assertFalse(self.f.orm.jobs)

    def test_pending_apply_has_no_invented_url_or_ready_status(self):
        self.f.advance(compute=self.compute)
        observation = self.observe()
        self.assertEqual(observation.phase, 'APPLY_ACCEPTED')
        self.assertIsNone(observation.context)

    def test_successful_base_exposes_owned_address_with_credentials_still_unconfigured(self):
        self.f.advance(compute=self.compute)
        job = self.f.orm.jobs[0]
        job['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.inventories[job['id']] = cloud_inventory()
        self.compute.instance['lifecycle-state'] = 'STOPPED'
        observation = self.observe()
        self.assertEqual(observation.context, CONTEXT)
        self.assertEqual(observation.phase, 'CREDENTIALS_NOT_BOUND')
        self.assertFalse(self.f.keys.created)

    def test_saved_history_with_absent_stack_stops_instead_of_claiming_new_scope(self):
        self.f.advance(compute=self.compute)
        self.f.orm.stacks.clear()
        with self.assertRaises(DeliveryError):
            self.observe()

    def test_changed_or_missing_stack_binding_cannot_report_attested_deployment(self):
        self.f.advance(compute=self.compute)
        self.f.orm.jobs[0]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.inventories[self.f.orm.jobs[0]['id']] = cloud_inventory()
        self.f.advance(compute=self.compute, external_api_key='synthetic-key',
                       demo_password='Synthetic9!password', expires_at=EXPIRES)
        job = self.f.orm.jobs[1]
        job['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.inventories[job['id']] = cloud_inventory()
        for binding in (None, job['variables']['oci_model_key_ocid'] + 'changed'):
            with self.subTest(binding=bool(binding)):
                if binding is None:
                    self.f.orm.stacks[0]['variables'].pop('oci_model_key_ocid', None)
                else:
                    self.f.orm.stacks[0]['variables']['oci_model_key_ocid'] = binding
                with self.assertRaises(DeliveryError):
                    self.observe()

    def test_changed_stack_package_tag_is_rejected(self):
        self.f.advance(compute=self.compute)
        self.f.orm.stacks[0]['freeform-tags']['package_hash'] = 'f' * 64
        with self.assertRaises(DeliveryError):
            self.observe()
