"""Publication requires successful attested permission and unchanged resource identity."""

import unittest
from copy import deepcopy

from deployment.credential_errors import DeliveryError
from .foundation_fixtures import archive_bytes
from .handoff_fixture import HandoffFixture
from .inventory_fixture import inventory
from .record_fixtures import KEY_ID
from .vault_fixture import record


class HandoffPublicationTests(unittest.TestCase):
    def setUp(self):
        self.f = HandoffFixture()

    def assert_unpublished(self):
        self.assertEqual(self.f.vault.current, 1)
        self.assertFalse(any(row[0] == 'promote' for row in self.f.vault.mutations))

    def test_exact_successful_permission_job_publishes_and_does_not_claim_ready(self):
        self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        result = self.f.advance()
        self.assertEqual(result.phase, 'CREDENTIALS_PUBLISHED')
        self.assertEqual((result.credentials.phase, result.job.model_key_ocid), ('CURRENT', KEY_ID))
        self.assertEqual(self.f.vault.current, result.credentials.version_number)
        self.assertIn(('get_job_package', result.job.job_id), self.f.orm.calls)
        self.assertIn(('list_job_resources', result.job.job_id, self.f.target.compartment_id),
                      self.f.orm.calls)

    def test_missing_base_inventory_prevents_key_creation(self):
        self.f.base_succeeded()
        self.f.orm.inventories[self.f.orm.jobs[0]['id']] = {'data': {'items': []}}
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(self.f.vault.mutations, [])
        self.assertEqual(len(self.f.orm.jobs), 1)

    def test_each_changed_bound_resource_blocks_publication(self):
        for index in range(3):
            self.f = HandoffFixture()
            self.f.permissions_started()
            self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
            response = inventory()
            response['data']['items'][index]['resource-id'] += 'changed'
            self.f.orm.inventories[self.f.orm.jobs[1]['id']] = response
            with self.subTest(index=index), self.assertRaises(DeliveryError):
                self.f.advance()
            self.assert_unpublished()

    def test_missing_successful_bound_inventory_fails_closed(self):
        self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.inventories[self.f.orm.jobs[1]['id']] = {'data': {'items': []}}
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assert_unpublished()

    def test_job_binding_mismatch_or_changed_archive_cannot_publish(self):
        self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        self.f.orm.jobs[1]['variables']['oci_model_key_ocid'] += 'changed'
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assert_unpublished()
        self.f.orm.jobs[1]['variables']['oci_model_key_ocid'] = KEY_ID
        self.f.orm.archives[self.f.orm.jobs[1]['id']] = archive_bytes(changed='variables.tf')
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assert_unpublished()

    def test_wrong_secret_ownership_prevents_new_credentials(self):
        self.f.base_succeeded()
        self.f.vault.metadata_overrides = {'vault-id': 'wrong'}
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(self.f.vault.mutations, [])

    def test_concurrent_current_replacement_is_preserved_without_retry(self):
        self.f.permissions_started()
        self.f.orm.jobs[1]['lifecycle-state'] = 'SUCCEEDED'
        other = record(operation_id='b' * 32)
        self.f.vault.before_promote = lambda vault: vault.add(other, current=True)
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.vault.rows[self.f.vault.current][0], other.version_name)
        self.assertEqual(sum(row[0] == 'promote' for row in self.f.vault.mutations), 1)

    def test_unrelated_active_job_blocks_before_credential_writes(self):
        self.f.base_succeeded()
        other = deepcopy(self.f.orm.jobs[0])
        other.update({'id': other['id'] + 'other', 'lifecycle-state': 'ACCEPTED', 'freeform-tags': {}})
        self.f.orm.jobs.append(other)
        with self.assertRaises(DeliveryError):
            self.f.advance()
        self.assertEqual(self.f.keys.created, [])
        self.assertEqual(self.f.vault.mutations, [])
