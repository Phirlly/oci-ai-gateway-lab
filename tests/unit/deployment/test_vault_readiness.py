"""Owned metadata uses one finite read budget while Vault updates complete."""

from copy import deepcopy
import traceback
import unittest
from unittest.mock import Mock, patch

from deployment.credential_errors import DeliveryError, VaultReadError
from deployment.vault_state import read_secret_metadata
from .vault_fixture import MemoryVault, delivery
from .vault_transport_fixture import MemoryVaultTransport


class VaultReadinessTests(unittest.TestCase):
    def setUp(self):
        self.vault = MemoryVault()
        self.target = delivery(self.vault).target
        self.active = self.vault.metadata(self.target.secret_id)
        self.updating = deepcopy(self.active)
        self.updating['data']['lifecycle-state'] = 'UPDATING'
        self.sleep = patch('time.sleep').start()
        self.addCleanup(patch.stopall)

    def test_returns_latest_active_etag_and_current_version(self):
        self.active['etag'] = 'final-etag'
        self.active['data']['current-version-number'] = 3
        self.vault.metadata = Mock(side_effect=[self.updating, self.active])
        self.assertEqual(read_secret_metadata(self.vault, self.target), ('final-etag', 3))
        self.assertEqual(self.vault.metadata.call_count, 2)
        self.sleep.assert_called_once_with(2)

    def test_wrong_owner_malformed_or_unsupported_state_never_waits(self):
        changes = ({'compartment-id': 'foreign'}, {'current-version-number': True},
                   {'freeform-tags': {}}, {'lifecycle-state': 'FAILED'})
        for changed in changes:
            with self.subTest(changed=changed):
                response = deepcopy(self.updating)
                response['data'].update(changed)
                self.vault.metadata = Mock(return_value=response)
                with self.assertRaises(DeliveryError):
                    read_secret_metadata(self.vault, self.target)
                self.assertEqual(self.vault.metadata.call_count, 1)
        self.sleep.assert_not_called()

    def test_transport_errors_and_updating_share_six_total_attempts(self):
        transport = MemoryVaultTransport(self.vault)
        transport.request = Mock(side_effect=[VaultReadError('secret-sentinel'), self.updating] * 3)
        with self.assertRaisesRegex(VaultReadError, 'readiness') as error:
            read_secret_metadata(transport, self.target)
        self.assertEqual(transport.request.call_count, 6)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4, 8, 16, 30])
        self.assertNotIn('sentinel', ''.join(traceback.format_exception(error.exception)))
        self.assertEqual(self.vault.mutations, [])

    def test_persistent_updating_stops_without_any_write(self):
        self.vault.metadata = Mock(return_value=self.updating)
        with self.assertRaisesRegex(VaultReadError, 'readiness'):
            read_secret_metadata(self.vault, self.target)
        self.assertEqual(self.vault.metadata.call_count, 6)
        self.assertEqual(self.vault.mutations, [])

    def test_ownership_change_during_wait_stops_immediately(self):
        self.active['data']['key-id'] = 'foreign'
        self.vault.metadata = Mock(side_effect=[self.updating, self.active])
        with self.assertRaises(DeliveryError):
            read_secret_metadata(self.vault, self.target)
        self.assertEqual(self.vault.metadata.call_count, 2)
        self.sleep.assert_called_once_with(2)
