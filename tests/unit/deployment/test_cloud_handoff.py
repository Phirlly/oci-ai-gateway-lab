"""VM/address attestation accompanies credentials across both infrastructure Applies."""

import json
import unittest
from pathlib import Path

from deployment.credential_errors import DeliveryError
from deployment.foundation_package import GatewayPackage
from deployment.gateway_config import GatewayConfig
from deployment.resource_manager_stacks import StackTarget
from .cloud_inventory_fixture import CloudMetadata, cloud_inventory
from .gateway_config_fixture import CONTEXT, GATEWAY_SETTINGS
from .handoff_fixture import HandoffFixture
from .record_fixtures import EXPIRES, IDENTITY


class CloudHandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = HandoffFixture()
        self.f.target = StackTarget(GatewayConfig({**GATEWAY_SETTINGS, 'inference_region': IDENTITY['inference_region']}),
                                    self.f.target.controller_id)
        self.f.package = GatewayPackage.build(Path(__file__).resolve().parents[3])
        self.f.orm.package = self.f.package
        self.compute = CloudMetadata()

    def advance(self, **inputs):
        return self.f.advance(compute=self.compute, **inputs)

    def begin_permissions(self):
        self.advance()
        base = self.f.orm.jobs[0]
        base['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.inventories[base['id']] = cloud_inventory()
        return self.advance(external_api_key='synthetic-api-key', demo_password='Synthetic9!password', expires_at=EXPIRES)

    def finish(self):
        job = self.f.orm.jobs[1]
        job['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.inventories[job['id']] = cloud_inventory()
        return self.advance()

    def test_published_bundle_binds_exact_runtime_and_rerun_preserves_it(self):
        self.begin_permissions()
        result = self.finish()
        saved = dict(self.f.vault.rows)
        content = json.loads(saved[self.f.vault.current][1])
        self.assertEqual(content['schema_version'], 2)
        self.assertEqual(content['runtime'], CONTEXT)
        self.assertEqual(result.phase, 'CREDENTIALS_PUBLISHED')
        self.assertEqual(result.runtime_context, CONTEXT)
        self.assertEqual(self.advance(), result)
        self.assertEqual(self.f.vault.rows, saved)
        self.assertEqual(len(self.f.keys.created), 1)

    def test_changed_public_address_prevents_reusing_saved_credentials(self):
        self.begin_permissions()
        self.compute.public['ip-address'] = '8.8.8.8'
        self.compute.vnic['public-ip'] = '8.8.8.8'
        with self.assertRaises(DeliveryError):
            self.finish()
        self.assertEqual(self.f.vault.current, 1)
        self.assertEqual(len(self.f.keys.created), 1)

    def test_permission_inventory_cannot_replace_instance_before_publication(self):
        self.begin_permissions()
        job = self.f.orm.jobs[1]
        job['lifecycle-state'] = 'SUCCEEDED'
        inventory = cloud_inventory()
        inventory['data']['items'][3]['resource-id'] += 'changed'
        self.f.orm.inventories[job['id']] = inventory
        with self.assertRaises(DeliveryError):
            self.advance()
        self.assertEqual(self.f.vault.current, 1)

    def test_complete_settings_require_full_package_and_compute_adapter_before_writes(self):
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertFalse(self.f.orm.stacks)

    def test_full_package_cannot_be_submitted_with_legacy_settings(self):
        f = HandoffFixture()
        f.package = self.f.package
        f.orm.package = self.f.package
        with self.assertRaises(DeliveryError):
            f.advance()
        self.assertFalse(f.orm.stacks)
        self.assertFalse(f.orm.jobs)
